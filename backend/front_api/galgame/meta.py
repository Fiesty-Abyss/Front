"""混合模式：按用户设置的来源顺序搜索、互相补全、合并字段。

- 单一来源模式：只用这个来源；它出错或没结果时，按顺序回退到下一个来源。
- 混合模式：同时搜索所有启用的来源；选中某一个结果后，用原名 / 标题在其余来源里自动找同一部作品
  （名称相似度够高、发售年份不冲突才算），再按来源顺序合并：每个字段取第一个有值的来源，
  别名、标签、链接取并集，各来源的评分分开保留。
任何一个来源失败都不影响其他来源，错误会原样返回给前端显示。
"""

from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.orm import Session

from .. import models as m
from . import sources as src

KEY = "galgame_settings"
DEFAULTS: dict[str, Any] = {
    "mode": "mixed",  # mixed / bangumi / vndb / ymgal
    "order": ["bangumi", "ymgal", "vndb"],  # 中文资料优先
    "enabled": {"bangumi": True, "vndb": True, "ymgal": True},
    "bangumi_token": "",  # 可选：Bangumi 个人令牌，登录后才能搜到 R18 条目
    "fetch_characters": True,
    "blur_nsfw": True,
    "auto_match": True,
}
SCALAR_FIELDS = ("title_cn", "original", "description", "developer", "release_date", "cover_url", "nsfw")


def load_settings(session: Session) -> dict[str, Any]:
    row = session.get(m.AppSetting, KEY)
    out = {**DEFAULTS, **(row.value if row and isinstance(row.value, dict) else {})}
    out["enabled"] = {**DEFAULTS["enabled"], **(out.get("enabled") or {})}
    order = [s for s in out.get("order") or [] if s in src.SOURCES]
    out["order"] = order + [s for s in src.SOURCES if s not in order]
    if out.get("mode") not in ("mixed", *src.SOURCES):
        out["mode"] = "mixed"
    return out


def public_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in cfg.items() if k != "bangumi_token"}
    out["has_bangumi_token"] = bool(cfg.get("bangumi_token"))
    out["online"] = src.enabled()
    out["labels"] = src.LABELS
    return out


def active_sources(cfg: dict[str, Any], only: str | None = None) -> list[str]:
    if only:
        return [only]
    on = [s for s in cfg["order"] if cfg["enabled"].get(s)]
    if cfg["mode"] in src.SOURCES:
        # 单一来源：它排第一，其余启用的来源作为回退
        on = [cfg["mode"]] + [s for s in on if s != cfg["mode"]]
    return on


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s\W_]+", "", s)


def similarity(a: str | None, b: str | None) -> float:
    x, y = _norm(a), _norm(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    if len(x) >= 4 and len(y) >= 4 and (x in y or y in x):
        return 0.9
    return SequenceMatcher(None, x, y).ratio()


def best_score(names: list[str | None], item: dict[str, Any]) -> float:
    cands = [item.get("title"), item.get("title_cn"), item.get("original")]
    return max((similarity(n, c) for n in names if n for c in cands if c), default=0.0)


def _search_one(source: str, q: str, cfg: dict[str, Any]) -> dict[str, Any]:
    t0 = datetime.now()
    try:
        items = src.search(source, q, cfg.get("bangumi_token") or None)
        return {"ok": True, "items": items, "error": None, "ms": int((datetime.now() - t0).total_seconds() * 1000)}
    except src.SourceError as e:
        return {"ok": False, "items": [], "error": str(e), "ms": int((datetime.now() - t0).total_seconds() * 1000)}


def search(q: str, cfg: dict[str, Any], only: str | None = None) -> dict[str, Any]:
    """返回 {mode, order, results: {source: {ok, items, error, ms}}, used}。"""
    order = active_sources(cfg, only)
    results: dict[str, Any] = {}
    if cfg["mode"] == "mixed" or only:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for s, r in zip(order, pool.map(lambda s: _search_one(s, q, cfg), order)):
                results[s] = r
    else:
        for s in order:  # 按顺序回退：直到某个来源有结果
            results[s] = _search_one(s, q, cfg)
            if results[s]["items"]:
                break
    used = [s for s in order if results.get(s, {}).get("items")]
    return {"mode": "single" if only else cfg["mode"], "order": order, "results": results, "used": used}


def _year(d: str | None) -> int | None:
    return int(d[:4]) if d and d[:4].isdigit() else None


def auto_match(first: dict[str, Any], others: list[str], cfg: dict[str, Any]) -> dict[str, Any]:
    """在其余来源里找同一部作品；返回 {source: {sid, score} | {error}}。"""
    names = [first.get("original"), first.get("title"), first.get("title_cn")] + (first.get("aliases") or [])[:3]
    queries = list(dict.fromkeys(n for n in names[:3] if n))
    year = _year(first.get("date") or first.get("release_date"))

    def one(source: str) -> tuple[str, dict[str, Any]]:
        last_err = None
        best: tuple[float, dict[str, Any] | None] = (0.0, None)
        for q in queries[:2]:
            r = _search_one(source, q, cfg)
            if not r["ok"]:
                last_err = r["error"]
                continue
            for it in r["items"]:
                sc = best_score(names, it)
                y = _year(it.get("date"))
                if year and y and abs(y - year) > 1:
                    sc -= 0.3
                if sc > best[0]:
                    best = (sc, it)
            if best[0] >= 0.95:
                break
        if best[1] is not None and best[0] >= 0.8:
            return source, {"sid": best[1]["sid"], "score": round(best[0], 2), "title": best[1].get("title")}
        return source, {"error": last_err} if last_err and best[1] is None else {"none": True}

    with ThreadPoolExecutor(max_workers=3) as pool:
        return dict(pool.map(one, others))


def fetch(picks: dict[str, str], cfg: dict[str, Any], match: bool | None = None) -> dict[str, Any]:
    """picks: {source: sid}。match 为真（混合模式默认）时自动补全其他来源。
    返回 {details: {source: detail}, errors: {source: msg}, matched: {...}, merged: {...}}。"""
    picks = {k: str(v) for k, v in picks.items() if k in src.SOURCES and v}
    token = cfg.get("bangumi_token") or None
    chars = bool(cfg.get("fetch_characters", True))
    details: dict[str, Any] = {}
    errors: dict[str, str] = {}

    def get(item: tuple[str, str]) -> tuple[str, Any]:
        s, sid = item
        try:
            return s, src.detail(s, sid, token, chars) or {"__missing__": True}
        except src.SourceError as e:
            return s, {"__error__": str(e)}

    def run(items: dict[str, str]) -> None:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for s, d in pool.map(get, items.items()):
                if d.get("__error__"):
                    errors[s] = d["__error__"]
                elif d.get("__missing__"):
                    errors[s] = f"{src.LABELS[s]}：找不到这个条目"
                else:
                    details[s] = d

    run(picks)
    matched: dict[str, Any] = {}
    do_match = cfg["mode"] == "mixed" and cfg.get("auto_match", True) if match is None else match
    if do_match and details:
        first = details[next(s for s in cfg["order"] if s in details)]
        others = [s for s in active_sources(cfg) if s not in picks]
        if others:
            matched = auto_match(first, others, cfg)
            run({s: v["sid"] for s, v in matched.items() if v.get("sid")})
            for s, v in matched.items():
                if v.get("error"):
                    errors.setdefault(s, v["error"])
    return {"details": details, "errors": errors, "matched": matched, "merged": merge(details, cfg["order"])}


_KANA = re.compile(r"[\u3040-\u30ff]")
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _prefer_chinese(texts: list[str | None]) -> str | None:
    """简介优先用中文的：假名占比低、汉字占比高的那一段；都不是就按来源顺序取第一个。"""
    texts = [t for t in texts if t]
    for t in texts:
        if len(_CJK.findall(t)) > len(t) * 0.2 and len(_KANA.findall(t)) < len(t) * 0.05:
            return t
    return texts[0] if texts else None


def merge(details: dict[str, Any], order: list[str]) -> dict[str, Any]:
    ds = [details[s] for s in order if s in details]
    if not ds:
        return {}

    def first(key: str) -> Any:
        return next((d.get(key) for d in ds if d.get(key) not in (None, "", [])), None)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    title_cn = first("title_cn")
    original = first("original")
    aliases = src._dedupe([a for d in ds for a in [d.get("title"), d.get("original"), *(d.get("aliases") or [])]])
    aliases = [a for a in aliases if a not in (title_cn, original)]
    links: list[dict[str, Any]] = []
    for d in ds:
        for ln in d.get("links") or []:
            if ln.get("url") and all(ln["url"].rstrip("/") != x["url"].rstrip("/") for x in links):
                links.append(ln)
    return {
        "title": title_cn or first("title") or original,
        "title_cn": title_cn, "original": original, "aliases": aliases[:30],
        "description": _prefer_chinese([d.get("description") for d in ds]), "developer": first("developer"),
        "release_date": first("date"), "platforms": src._dedupe([p for d in ds for p in d.get("platforms") or []], 20),
        "source_tags": src._dedupe([t for d in ds for t in d.get("tags") or []], 40),
        "nsfw": any(d.get("nsfw") for d in ds), "cover_url": first("cover"),
        "characters": first("characters") or [],
        "links": links[:20],
        "sources": {d["source"]: {"id": d["sid"], "url": d["url"], "score": d.get("score"), "rank": d.get("rank"),
                                  "votes": d.get("votes"), "length_minutes": d.get("length_minutes"),
                                  "has_chinese": d.get("has_chinese"), "title": d.get("title"), "fetched_at": now}
                    for d in ds},
    }
