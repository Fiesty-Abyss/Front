"""世界书（Lorebook / World Info）：关键词命中 → 把条目内容注入对话上下文。

规则与 SillyTavern / Character Card V2 的 character_book 基本一致：
- 扫描最近 scan_depth 条消息；任意一个主关键词命中即激活（keys 支持 /正则/flags 写法）
- selective：还要求任意一个次关键词命中
- constant：始终激活
- recursive：已激活条目的内容也参与下一轮扫描（最多 3 轮）
- token_budget：超出预算时按 常驻 > 优先级 > 插入顺序 取舍
"""

from __future__ import annotations

import re
from typing import Any

CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]")
POSITIONS = ("before_char", "after_char")


def estimate_tokens(text: str) -> int:
    """粗略估算 token：中日韩文字按 1 字 1 token，其余按 4 个字符 1 token。"""
    if not text:
        return 0
    cjk = len(CJK.findall(text))
    return cjk + (len(text) - cjk + 3) // 4


def _g(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def match_key(key: str, text: str, case_sensitive: bool = False) -> bool:
    key = (key or "").strip()
    if not key:
        return False
    rx = re.fullmatch(r"/(.+)/([imsx]*)", key, re.S)
    if rx:
        flags = 0
        for ch in rx.group(2):
            flags |= {"i": re.I, "m": re.M, "s": re.S, "x": re.X}[ch]
        if not case_sensitive and not rx.group(2):
            flags |= re.I
        try:
            return re.search(rx.group(1), text, flags) is not None
        except re.error:
            return False
    if re.fullmatch(r"[A-Za-z0-9_ ]+", key):
        # 纯英文关键词按整词匹配，避免 cat 命中 category
        pattern = r"(?<![A-Za-z0-9_])" + re.escape(key) + r"(?![A-Za-z0-9_])"
        return re.search(pattern, text, 0 if case_sensitive else re.I) is not None
    if case_sensitive:
        return key in text
    return key.casefold() in text.casefold()


def _hit(entry: Any, text: str) -> str | None:
    cs = bool(_g(entry, "case_sensitive", False))
    primary = next((k for k in _g(entry, "keys", []) or [] if match_key(k, text, cs)), None)
    if primary is None:
        return None
    secondary = _g(entry, "secondary_keys", []) or []
    if _g(entry, "selective", False) and secondary:
        sec = next((k for k in secondary if match_key(k, text, cs)), None)
        if sec is None:
            return None
        return f"{primary} + {sec}"
    return primary


def activate_book(book: Any, texts: list[str]) -> dict[str, list[dict[str, Any]]]:
    depth = int(_g(book, "scan_depth", 4) or 0)
    scan = "\n".join(texts[-depth:]) if depth > 0 else ""
    entries = [e for e in (_g(book, "entries", []) or []) if _g(e, "enabled", True) and (_g(e, "content", "") or "").strip()]
    active: dict[Any, str] = {}
    for e in entries:
        if _g(e, "constant", False):
            active[id(e)] = "常驻"
    rounds = 3 if _g(book, "recursive", False) else 1
    for _ in range(rounds):
        new = False
        for e in entries:
            if id(e) in active:
                continue
            key = _hit(e, scan)
            if key is not None:
                active[id(e)] = f"关键词：{key}"
                new = True
        if not new or rounds == 1:
            break
        scan = scan + "\n" + "\n".join(_g(e, "content", "") for e in entries if id(e) in active)
    picked = [e for e in entries if id(e) in active]
    picked.sort(key=lambda e: (not _g(e, "constant", False), -int(_g(e, "priority", 10) or 0), int(_g(e, "insertion_order", 100) or 0)))
    budget = int(_g(book, "token_budget", 1024) or 0)
    used, kept, skipped = 0, [], []
    for e in picked:
        tokens = estimate_tokens(_g(e, "content", ""))
        row = {
            "entry_id": _g(e, "id"), "lorebook_id": _g(book, "id"), "lorebook": _g(book, "name", ""),
            "title": _g(e, "title", "") or ", ".join((_g(e, "keys", []) or [])[:2]),
            "content": _g(e, "content", ""), "position": _g(e, "position", "before_char") or "before_char",
            "insertion_order": int(_g(e, "insertion_order", 100) or 0), "reason": active[id(e)], "tokens": tokens,
        }
        if budget and used + tokens > budget:
            skipped.append(row)
            continue
        used += tokens
        kept.append(row)
    kept.sort(key=lambda r: r["insertion_order"])
    return {"active": kept, "skipped": skipped}


def activate(books: list[Any], texts: list[str]) -> dict[str, Any]:
    active, skipped = [], []
    for book in books:
        res = activate_book(book, texts)
        active += res["active"]
        skipped += res["skipped"]
    active.sort(key=lambda r: r["insertion_order"])
    return {"active": active, "skipped": skipped, "tokens": sum(r["tokens"] for r in active)}


def split_positions(active: list[dict[str, Any]]) -> dict[str, str]:
    out = {}
    for pos in POSITIONS:
        out[pos] = "\n\n".join(r["content"].strip() for r in active if r["position"] == pos)
    return out


# ---------- 格式互转 ----------
def entry_from_v2(e: dict[str, Any], index: int = 0) -> dict[str, Any]:
    """Character Card V2 character_book 的条目，或 SillyTavern 世界书（world info）条目 -> 字段。"""
    if "key" in e or "keysecondary" in e or "uid" in e:  # SillyTavern world info
        pos = e.get("position", 0)
        return {
            "title": str(e.get("comment") or "")[:200],
            "keys": [str(k) for k in e.get("key") or [] if str(k).strip()],
            "secondary_keys": [str(k) for k in e.get("keysecondary") or [] if str(k).strip()],
            "selective": bool(e.get("selective", False)) and bool(e.get("keysecondary")),
            "content": str(e.get("content") or ""),
            "enabled": not bool(e.get("disable", False)),
            "constant": bool(e.get("constant", False)),
            "case_sensitive": bool(e.get("caseSensitive") or False),
            "insertion_order": int(e.get("order", 100) or 0),
            "priority": int(e.get("priority", 10) or 10) if isinstance(e.get("priority"), (int, float)) else 10,
            "position": "after_char" if pos in (1, "after_char") else "before_char",
            "extensions": {k: v for k, v in e.items() if k in ("probability", "depth", "group")},
        }
    pos = e.get("position") or "before_char"
    return {
        "title": str(e.get("name") or e.get("comment") or "")[:200],
        "keys": [str(k) for k in e.get("keys") or [] if str(k).strip()],
        "secondary_keys": [str(k) for k in e.get("secondary_keys") or [] if str(k).strip()],
        "selective": bool(e.get("selective", False)),
        "content": str(e.get("content") or ""),
        "enabled": bool(e.get("enabled", True)),
        "constant": bool(e.get("constant", False)),
        "case_sensitive": bool(e.get("case_sensitive") or False),
        "insertion_order": int(e.get("insertion_order", index * 10) or 0),
        "priority": int(e.get("priority", 10) or 10),
        "position": pos if pos in POSITIONS else "before_char",
        "extensions": dict(e.get("extensions") or {}),
    }


def book_from_json(payload: dict[str, Any]) -> dict[str, Any]:
    """接受 V2 character_book、SillyTavern 世界书，或带 character_book 的角色卡 JSON。"""
    if not isinstance(payload, dict):
        raise ValueError("世界书 JSON 必须是对象")
    if payload.get("spec") in ("chara_card_v2", "chara_card_v3"):
        book = (payload.get("data") or {}).get("character_book")
        if not book:
            raise ValueError("这张角色卡没有附带世界书（character_book）")
        payload = dict(book, name=book.get("name") or f"{payload['data'].get('name', '')} 的世界书")
    entries = payload.get("entries")
    if isinstance(entries, dict):  # SillyTavern：{"0": {...}, "1": {...}}
        entries = list(entries.values())
    if not isinstance(entries, list):
        raise ValueError("没有找到 entries 字段")
    return {
        "name": str(payload.get("name") or "导入的世界书")[:200],
        "description": payload.get("description") or None,
        "scan_depth": int(payload.get("scan_depth") or 4),
        "token_budget": int(payload.get("token_budget") or 1024),
        "recursive": bool(payload.get("recursive_scanning", False)),
        "extensions": dict(payload.get("extensions") or {}),
        "entries": [entry_from_v2(e, i) for i, e in enumerate(entries) if isinstance(e, dict)],
    }


def book_to_v2(book: Any) -> dict[str, Any]:
    return {
        "name": book.name, "description": book.description or "", "scan_depth": book.scan_depth,
        "token_budget": book.token_budget, "recursive_scanning": book.recursive, "extensions": dict(book.extensions or {}),
        "entries": [
            {
                "keys": list(e.keys or []), "content": e.content, "extensions": dict(e.extensions or {}),
                "enabled": e.enabled, "insertion_order": e.insertion_order, "case_sensitive": e.case_sensitive,
                "name": e.title, "priority": e.priority, "id": e.id, "comment": e.title, "selective": e.selective,
                "secondary_keys": list(e.secondary_keys or []), "constant": e.constant, "position": e.position,
            }
            for e in book.entries
        ],
    }


def book_to_st(book: Any) -> dict[str, Any]:
    """SillyTavern 世界书格式（可直接在 SillyTavern 的 World Info 里导入）。"""
    entries = {}
    for i, e in enumerate(book.entries):
        entries[str(i)] = {
            "uid": i, "key": list(e.keys or []), "keysecondary": list(e.secondary_keys or []), "comment": e.title,
            "content": e.content, "constant": e.constant, "selective": e.selective, "order": e.insertion_order,
            "position": 1 if e.position == "after_char" else 0, "disable": not e.enabled,
            "caseSensitive": e.case_sensitive, "priority": e.priority,
        }
    return {"name": book.name, "description": book.description or "", "entries": entries}
