"""从小说 / 设定正文里抽取角色：分段交给模型，按名字与别名合并结果。"""

from __future__ import annotations

import json
import re
from typing import Any

from ..chapters import split_chapters

TASK_MARK = "[FRONT_TASK:extract_characters]"
GENDER_MAP = {"男": "male", "male": "male", "m": "male", "女": "female", "female": "female", "f": "female",
              "其他": "other", "other": "other"}


def chunk_text(text: str, size: int = 3000) -> list[str]:
    """先按章节切，再把短章节拼起来、长章节按段落拆开，每段不超过 size 字。"""
    text = text or ""
    parts: list[str] = []
    chapters = split_chapters(text)
    pieces = [text[c["start"]:c["end"]].strip("\n") for c in chapters] if chapters else [text]  # 保留章节标题
    for piece in pieces:
        if len(piece) <= size:
            parts.append(piece)
            continue
        buf = ""
        for para in piece.split("\n"):
            if len(buf) + len(para) + 1 > size and buf:
                parts.append(buf)
                buf = ""
            while len(para) > size:
                parts.append(para[:size])
                para = para[size:]
            buf = f"{buf}\n{para}" if buf else para
        if buf:
            parts.append(buf)
    out: list[str] = []
    for p in parts:
        if not p.strip():
            continue
        if out and len(out[-1]) + len(p) + 1 <= size:
            out[-1] = out[-1] + "\n" + p
        else:
            out.append(p)
    return out


def build_messages(chunk: str, known: list[str]) -> list[dict[str, str]]:
    known_line = "、".join(known[:80]) if known else "（无）"
    return [
        {"role": "system", "content": (
            f"{TASK_MARK}\n你是小说设定整理助手。阅读用户给出的小说片段，找出其中出现的有名字的角色。"
            "只输出 JSON，不要任何解释，格式："
            '{"characters":[{"name":"名字","aliases":["别名"],"gender":"男|女|未知","summary":"一句话简介",'
            '"traits":["性格或身份关键词"],"appearance":"外貌（没有就留空）",'
            '"relations":[{"target":"另一个角色名","kind":"关系，如 兄妹/同学/对手","evidence":"原文依据"}]}]}。'
            "只写文本中有依据的内容，不要编造；地名、组织名不是角色。"
        )},
        {"role": "user", "content": f"已知角色（若出现请沿用同一名字）：{known_line}\n\n小说片段：\n{chunk}"},
    ]


def _list(v: Any) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[、,，/;；]", v)
    return [str(x).strip() for x in v or [] if str(x).strip()]


def parse(text: str) -> list[dict[str, Any]]:
    match = re.search(r"\{.*\}|\[.*\]", text or "", re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    items = data.get("characters") if isinstance(data, dict) else data
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()[:200]
        if not name:
            continue
        rels = []
        for r in it.get("relations") or []:
            if isinstance(r, dict) and str(r.get("target") or "").strip():
                rels.append({"target": str(r["target"]).strip()[:200], "kind": str(r.get("kind") or "相关").strip()[:60],
                             "evidence": str(r.get("evidence") or "").strip()[:300]})
        out.append({
            "name": name,
            "aliases": [a for a in _list(it.get("aliases")) if a != name][:10],
            "gender": GENDER_MAP.get(str(it.get("gender") or "").strip().lower(), "unknown"),
            "summary": str(it.get("summary") or "").strip()[:500],
            "traits": _list(it.get("traits"))[:12],
            "appearance": str(it.get("appearance") or "").strip()[:500],
            "relations": rels[:20],
        })
    return out


def merge(acc: list[dict[str, Any]], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def find(name: str, aliases: list[str]) -> dict[str, Any] | None:
        names = {name, *aliases}
        for c in acc:
            if names & {c["name"], *c["aliases"]}:
                return c
        return None

    for it in items:
        cur = find(it["name"], it["aliases"])
        if cur is None:
            acc.append(dict(it, mentions=1))
            continue
        cur["mentions"] = cur.get("mentions", 1) + 1
        for a in [it["name"], *it["aliases"]]:
            if a != cur["name"] and a not in cur["aliases"]:
                cur["aliases"].append(a)
        if len(it["summary"]) > len(cur["summary"]):
            cur["summary"] = it["summary"]
        if not cur["appearance"]:
            cur["appearance"] = it["appearance"]
        if cur["gender"] == "unknown":
            cur["gender"] = it["gender"]
        cur["traits"] = list(dict.fromkeys(cur["traits"] + it["traits"]))[:12]
        seen = {(r["target"], r["kind"]) for r in cur["relations"]}
        cur["relations"] += [r for r in it["relations"] if (r["target"], r["kind"]) not in seen]
    return acc


def profile_markdown(c: dict[str, Any]) -> str:
    lines = []
    if c.get("traits"):
        lines.append("**特征**：" + "、".join(c["traits"]))
    if c.get("appearance"):
        lines.append("**外貌**：" + c["appearance"])
    if c.get("source"):
        lines.append(f"\n> 由 AI 从《{c['source']}》抽取，请人工核对。")
    return "\n\n".join(lines)
