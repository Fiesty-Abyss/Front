"""小说章节拆分与字数统计。"""

from __future__ import annotations

import re
import hashlib
from typing import Any

_NUM = "0-9０-９零一二三四五六七八九十百千万两〇"
HEADING_PATTERNS = [
    re.compile(rf"^[ \t\u3000]*(第[{_NUM}]+[章节回卷集部篇话][^\n]{{0,40}}?)[ \t\u3000]*$", re.M),
    re.compile(r"^[ \t]*((?:chapter|ch\.)\s*\d+[^\n]{0,60}?)[ \t]*$", re.M | re.I),
    re.compile(r"^[ \t]*#{1,6}[ \t]+([^\n]+?)[ \t]*$", re.M),
    re.compile(r"^[ \t\u3000]*((?:序章|楔子|尾声|终章|后记|序言|引子|番外)[^\n]{0,30}?|prologue|epilogue)[ \t\u3000]*$", re.M | re.I),
]
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_WORD = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")


def count_words(text: str) -> int:
    """中日文按字计，英文按词计。"""
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    latin = len(_WORD.findall(_CJK.sub(" ", text)))
    return cjk + latin


def split_chapters(text: str) -> list[dict[str, Any]]:
    text = text or ""
    marks: dict[int, tuple[int, str]] = {}
    # Ignore headings inside Markdown fenced code, preserving original offsets/line endings.
    fence_char, fence_length, fence_start, excluded = '', 0, 0, []
    for match in re.finditer(r'^[ \t]*(`{3,}|~{3,})[^\n]*', text, re.M):
        token = match.group(1)
        if not fence_char:
            fence_char, fence_length, fence_start = token[0], len(token), match.start()
        elif token[0] == fence_char and len(token) >= fence_length:
            excluded.append((fence_start, match.end()))
            fence_char = ''
    if fence_char:
        excluded.append((fence_start, len(text)))
    for rx in HEADING_PATTERNS:
        for m in rx.finditer(text):
            marks.setdefault(m.start(), (m.end(), m.group(1).strip().rstrip('#').strip()))
    if excluded:
        from bisect import bisect_right
        blocked = [a for a, b in excluded]
        marks = {s: v for s, v in marks.items() if not ((i := bisect_right(blocked, s) - 1) >= 0 and s < excluded[i][1])}
    starts = sorted(marks)
    chapters: list[dict[str, Any]] = []
    if not starts:
        return [{"index": 0, "title": "正文", "start": 0, "end": len(text), "words": count_words(text)}]
    if text[: starts[0]].strip():
        chapters.append({"title": "前言", "start": 0, "end": starts[0]})
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chapters.append({"title": marks[s][1], "start": 0 if i == 0 and not chapters else s, "end": end, "body_start": marks[s][0]})
    for i, ch in enumerate(chapters):
        ch["index"] = i
        ch["words"] = count_words(text[ch.get("body_start", ch["start"]): ch["end"]])
    return chapters


def chapter_text(text: str, chapter: dict[str, Any]) -> str:
    if 'body_start' in chapter:
        return text[chapter['body_start']:chapter['end']].strip('\r\n')
    body = text[chapter["start"]: chapter["end"]]
    # 去掉标题行本身，阅读器单独显示标题
    first, _, rest = body.partition("\n")
    if first.strip().lstrip("#").strip() == chapter["title"]:
        body = rest
    return body.strip("\n")


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def validate_plan(text: str, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Display order may differ from source order; every original character stays covered."""
    if not chapters or len(chapters) > 5000:
        raise ValueError('目录必须包含 1–5000 个章节')
    result = []
    for index, c in enumerate(chapters):
        start, end = c['start'], c['end']
        body = c.get('body_start', start)
        if not (0 <= start <= body <= end <= len(text)) or (start == end and text):
            raise ValueError('章节边界超出正文或章节为空')
        if body > start and not any(rx.fullmatch(text[start:body].strip()) for rx in HEADING_PATTERNS):
            raise ValueError('正文起点只能略过完整的已识别标题；手动分界应从新起点读取正文')
        title = c['title'].strip()
        if not title or len(title) > 300:
            raise ValueError('章节标题须为 1–300 字')
        result.append({'index': index, 'title': title, 'start': start, 'end': end, 'body_start': body,
                       'words': count_words(text[body:end])})
    cursor = 0
    for c in sorted(result, key=lambda c: c['start']):
        if c['start'] != cursor:
            raise ValueError('章节不能重叠或遗漏正文；合并/拆分时请同时调整相邻边界')
        cursor = c['end']
    if cursor != len(text):
        raise ValueError('章节必须覆盖全部正文')
    return result
