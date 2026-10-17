"""小说章节拆分与字数统计。"""

from __future__ import annotations

import re
from typing import Any

_NUM = "0-9０-９零一二三四五六七八九十百千万两〇"
HEADING_PATTERNS = [
    re.compile(rf"^[ \t\u3000]*(第[{_NUM}]+[章节回卷集部篇话][^\n]{{0,40}}?)[ \t\u3000]*$", re.M),
    re.compile(r"^[ \t]*((?:chapter|ch\.)\s*\d+[^\n]{0,60}?)[ \t]*$", re.M | re.I),
    re.compile(r"^[ \t]*#{1,3}[ \t]+([^\n]+?)[ \t]*$", re.M),
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
    for rx in HEADING_PATTERNS:
        for m in rx.finditer(text):
            marks.setdefault(m.start(), (m.end(), m.group(1).strip()))
    starts = sorted(marks)
    chapters: list[dict[str, Any]] = []
    if not starts:
        return [{"index": 0, "title": "正文", "start": 0, "end": len(text), "words": count_words(text)}]
    if text[: starts[0]].strip():
        chapters.append({"title": "前言", "start": 0, "end": starts[0]})
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chapters.append({"title": marks[s][1], "start": s, "end": end, "body_start": marks[s][0]})
    for i, ch in enumerate(chapters):
        ch["index"] = i
        ch["words"] = count_words(text[ch.get("body_start", ch["start"]): ch["end"]])
        ch.pop("body_start", None)
    return chapters


def chapter_text(text: str, chapter: dict[str, Any]) -> str:
    body = text[chapter["start"]: chapter["end"]]
    # 去掉标题行本身，阅读器单独显示标题
    first, _, rest = body.partition("\n")
    if first.strip().lstrip("#").strip() == chapter["title"]:
        body = rest
    return body.strip("\n")
