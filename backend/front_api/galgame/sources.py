"""三个元数据来源的客户端。每个来源都把结果整理成同一种结构：

候选（search）：{source, sid, title, title_cn, original, date, developer, cover, score, nsfw, url}
详情（detail）：候选字段 + aliases, description, tags, platforms, rank, votes, length_minutes,
              has_chinese, characters[{name, original, role, image, cv, description}], links[{title, url}]

只在用户主动搜索 / 添加 / 刷新时联网；FRONT_GALGAME=off 可完全关闭。
各来源的地址可以用环境变量改（测试和示例截图指向本地的 mock_galgame）。
"""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Any, Callable

import httpx

from .. import __version__

SOURCES = ("bangumi", "vndb", "ymgal")
LABELS = {"bangumi": "Bangumi", "vndb": "VNDB", "ymgal": "月幕 Galgame"}
USER_AGENT = f"Fiesty-Abyss/Front/{__version__} (https://github.com/Fiesty-Abyss/Front)"

# 测试时替换成 MockTransport / TestClient 的工厂
client_factory: Callable[[], httpx.Client] = lambda: httpx.Client(timeout=15, follow_redirects=True)  # noqa: E731


class SourceError(RuntimeError):
    def __init__(self, source: str, message: str):
        super().__init__(f"{LABELS.get(source, source)}：{message}")
        self.source = source


def enabled() -> bool:
    return os.environ.get("FRONT_GALGAME", "on").lower() not in ("0", "off", "false", "no")


def base(source: str) -> str:
    env = {"bangumi": "FRONT_BANGUMI_API", "vndb": "FRONT_VNDB_API", "ymgal": "FRONT_YMGAL_API"}[source]
    default = {"bangumi": "https://api.bgm.tv", "vndb": "https://api.vndb.org/kana",
               "ymgal": "https://www.ymgal.games"}[source]
    return (os.environ.get(env) or default).rstrip("/")


def _request(source: str, method: str, url: str, **kw: Any) -> Any:
    if not enabled():
        raise SourceError(source, "联网元数据已关闭（FRONT_GALGAME=off）")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **kw.pop("headers", {})}
    try:
        with client_factory() as c:
            r = c.request(method, url, headers=headers, **kw)
    except httpx.HTTPError as e:
        raise SourceError(source, f"连接失败（{type(e).__name__}）") from e
    if r.status_code == 429:
        raise SourceError(source, "请求太频繁，请稍后再试")
    if r.status_code == 401:
        raise SourceError(source, "认证失败（401）")
    if r.status_code == 404:
        return None
    if r.status_code >= 400:
        raise SourceError(source, f"HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError as e:
        raise SourceError(source, "返回的不是 JSON") from e


def _clean(text: str | None, limit: int = 6000) -> str | None:
    if not text:
        return None
    t = re.sub(r"\[url=[^\]]*\](.*?)\[/url\]", r"\1", text, flags=re.S)  # VNDB 的 BBCode 链接
    t = re.sub(r"\[/?(?:spoiler|b|i|u|s|quote|raw|code)\]", "", t)
    t = t.replace("\r\n", "\n").strip()
    return t[:limit] or None


def _date(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", v)
    if not m or m.group(1) in ("0000", "9999"):
        return None
    return "-".join(p for p in m.groups() if p)


def _dedupe(items: list[str], limit: int = 50) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for i in items:
        i = (i or "").strip()
        if i and i.lower() not in seen:
            seen.add(i.lower())
            out.append(i)
    return out[:limit]


# ---------------------------------------------------------------- Bangumi
def _bgm_headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _infobox(subject: dict[str, Any], *keys: str) -> list[str]:
    out: list[str] = []
    for row in subject.get("infobox") or []:
        if row.get("key") in keys:
            v = row.get("value")
            if isinstance(v, str):
                out += [p.strip() for p in re.split(r"[、/,，]", v) if p.strip()] if row.get("key") == "平台" else [v]
            elif isinstance(v, list):
                for x in v:
                    if isinstance(x, dict) and x.get("v"):
                        out += [p.strip() for p in re.split(r"[、]", x["v"]) if p.strip()]
    return out


def _bgm_item(d: dict[str, Any]) -> dict[str, Any]:
    imgs = d.get("images") or {}
    rating = d.get("rating") or {}
    dev = _infobox(d, "开发", "游戏开发商", "开发商", "品牌")
    return {
        "source": "bangumi", "sid": str(d.get("id")), "title": d.get("name_cn") or d.get("name"),
        "title_cn": d.get("name_cn") or None, "original": d.get("name") or None, "date": _date(d.get("date")),
        "developer": dev[0] if dev else None, "cover": imgs.get("large") or imgs.get("common") or d.get("image"),
        "score": rating.get("score") or None, "nsfw": bool(d.get("nsfw")),
        "url": f"https://bgm.tv/subject/{d.get('id')}",
    }


def bangumi_search(q: str, token: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    data = _request("bangumi", "POST", f"{base('bangumi')}/v0/search/subjects", params={"limit": limit},
                    json={"keyword": q, "filter": {"type": [4]}}, headers=_bgm_headers(token)) or {}
    return [_bgm_item(d) for d in data.get("data") or [] if d.get("id")]


def bangumi_detail(sid: str, token: str | None = None, characters: bool = True) -> dict[str, Any] | None:
    d = _request("bangumi", "GET", f"{base('bangumi')}/v0/subjects/{int(sid)}", headers=_bgm_headers(token))
    if not d:
        return None
    out = _bgm_item(d)
    rating = d.get("rating") or {}
    out.update({
        "aliases": _dedupe(_infobox(d, "别名", "中文名") + ([d["name"]] if d.get("name_cn") and d.get("name") else [])),
        "description": _clean(d.get("summary")),
        "tags": _dedupe([t.get("name") for t in sorted(d.get("tags") or [], key=lambda t: -(t.get("count") or 0))], 30),
        "platforms": _dedupe(_infobox(d, "平台")),
        "rank": rating.get("rank") or None, "votes": rating.get("total") or None, "length_minutes": None,
        "has_chinese": None, "links": [{"title": "Bangumi", "url": out["url"]}]
        + [{"title": "官方网站", "url": u} for u in _infobox(d, "官方网站", "website") if u.startswith("http")][:1],
        "characters": [],
    })
    if characters:
        rows = _request("bangumi", "GET", f"{base('bangumi')}/v0/subjects/{int(sid)}/characters",
                        headers=_bgm_headers(token)) or []
        for c in rows[:60]:
            imgs = c.get("images") or {}
            out["characters"].append({
                "name": c.get("name"), "original": None,
                "role": "main" if c.get("relation") == "主角" else "side",
                "image": imgs.get("medium") or imgs.get("grid") or None,
                "cv": "、".join(a.get("name") for a in c.get("actors") or [] if a.get("name")) or None,
                "description": None, "url": f"https://bgm.tv/character/{c.get('id')}" if c.get("id") else None,
            })
        out["characters"].sort(key=lambda c: c["role"] != "main")
    return out


# ---------------------------------------------------------------- VNDB
VN_FIELDS = ("title, alttitle, titles.title, titles.lang, titles.main, released, developers.name, "
             "image.url, image.sexual, rating, votecount")
VN_DETAIL = VN_FIELDS + (", aliases, description, length_minutes, platforms, languages, tags.name, tags.rating, "
                         "tags.spoiler, extlinks.url, extlinks.label, va.character.id, va.staff.name")


VN_PLATFORMS = {"win": "Windows", "mac": "macOS", "lin": "Linux", "ios": "iOS", "and": "Android", "web": "Web",
                "swi": "Nintendo Switch", "ps4": "PS4", "ps5": "PS5", "psv": "PS Vita", "psp": "PSP", "ps3": "PS3",
                "xb1": "Xbox One", "xbs": "Xbox Series", "dvd": "DVD 播放器", "mob": "手机"}


def _vn_item(d: dict[str, Any]) -> dict[str, Any]:
    titles = d.get("titles") or []
    cn = next((t.get("title") for t in titles if (t.get("lang") or "").startswith("zh")), None)
    img = d.get("image") or {}
    devs = [x.get("name") for x in d.get("developers") or [] if x.get("name")]
    return {
        "source": "vndb", "sid": d.get("id"), "title": cn or d.get("title"), "title_cn": cn,
        "original": d.get("alttitle") or d.get("title"), "date": _date(d.get("released")),
        "developer": devs[0] if devs else None, "cover": img.get("url"),
        "score": round(d["rating"] / 10, 2) if d.get("rating") else None,
        "nsfw": (img.get("sexual") or 0) >= 1.5, "url": f"https://vndb.org/{d.get('id')}",
    }


def vndb_search(q: str, limit: int = 10) -> list[dict[str, Any]]:
    data = _request("vndb", "POST", f"{base('vndb')}/vn", json={
        "filters": ["search", "=", q], "fields": VN_FIELDS, "results": limit, "sort": "searchrank"}) or {}
    return [_vn_item(d) for d in data.get("results") or [] if d.get("id")]


def vndb_detail(sid: str, characters: bool = True) -> dict[str, Any] | None:
    if not re.fullmatch(r"v\d+", sid):
        raise SourceError("vndb", f"不是 VNDB 的作品 id：{sid}")
    data = _request("vndb", "POST", f"{base('vndb')}/vn", json={
        "filters": ["id", "=", sid], "fields": VN_DETAIL, "results": 1}) or {}
    rows = data.get("results") or []
    if not rows:
        return None
    d = rows[0]
    out = _vn_item(d)
    tags = [t for t in d.get("tags") or [] if (t.get("spoiler") or 0) == 0 and (t.get("rating") or 0) >= 1.5]
    out.update({
        "aliases": _dedupe([t.get("title") for t in d.get("titles") or []] + (d.get("aliases") or [])),
        "description": _clean(d.get("description")),
        "tags": _dedupe([t.get("name") for t in sorted(tags, key=lambda t: -(t.get("rating") or 0))], 30),
        "platforms": [VN_PLATFORMS.get(p, p) for p in d.get("platforms") or []], "rank": None, "votes": d.get("votecount"),
        "length_minutes": d.get("length_minutes"),
        "has_chinese": any((x or "").startswith("zh") for x in d.get("languages") or []),
        "links": [{"title": "VNDB", "url": out["url"]}]
        + [{"title": x.get("label") or "链接", "url": x.get("url")} for x in d.get("extlinks") or []
           if (x.get("url") or "").startswith("http")][:6],
        "characters": [],
    })
    if characters:
        cv: dict[str, list[str]] = {}
        for va in d.get("va") or []:
            cid = (va.get("character") or {}).get("id")
            if cid and (va.get("staff") or {}).get("name"):
                cv.setdefault(cid, []).append(va["staff"]["name"])
        chars = _request("vndb", "POST", f"{base('vndb')}/character", json={
            "filters": ["vn", "=", ["id", "=", sid]], "results": 60,
            "fields": "name, original, description, image.url, image.sexual, vns.id, vns.role"}) or {}
        for c in chars.get("results") or []:
            role = next((v.get("role") for v in c.get("vns") or [] if v.get("id") == sid), "side")
            img = c.get("image") or {}
            out["characters"].append({
                "name": c.get("name"), "original": c.get("original"),
                "role": "main" if role in ("main", "primary") else "side",
                "image": img.get("url") if (img.get("sexual") or 0) < 1.5 else None,
                "cv": "、".join(cv.get(c.get("id"), [])) or None,
                "description": _clean(c.get("description"), 1200), "url": f"https://vndb.org/{c.get('id')}",
            })
        out["characters"].sort(key=lambda c: c["role"] != "main")
    return out


# ---------------------------------------------------------------- 月幕 ymgal
# 月幕文档公开的公共客户端凭证（https://www.ymgal.games/developer），可用环境变量换成自己申请的。
_ymgal_token: dict[str, Any] = {"token": None, "exp": 0.0, "base": None}
_ymgal_lock = threading.Lock()


def _ymgal_auth(force: bool = False) -> str:
    with _ymgal_lock:
        b = base("ymgal")
        if not force and _ymgal_token["token"] and _ymgal_token["exp"] > time.time() and _ymgal_token["base"] == b:
            return _ymgal_token["token"]
        data = _request("ymgal", "GET", f"{b}/oauth/token", params={
            "grant_type": "client_credentials", "scope": "public",
            "client_id": os.environ.get("FRONT_YMGAL_CLIENT_ID", "ymgal"),
            "client_secret": os.environ.get("FRONT_YMGAL_CLIENT_SECRET", "luna0327")}) or {}
        if not data.get("access_token"):
            raise SourceError("ymgal", "获取访问令牌失败")
        _ymgal_token.update(token=data["access_token"], exp=time.time() + min(int(data.get("expires_in") or 3600), 3600) - 60, base=b)
        return data["access_token"]


def _ymgal(path: str, params: dict[str, Any]) -> Any:
    for attempt in (0, 1):
        token = _ymgal_auth(force=attempt == 1)
        try:
            data = _request("ymgal", "GET", f"{base('ymgal')}{path}", params=params, headers={
                "Accept": "application/json;charset=utf-8", "Authorization": f"Bearer {token}", "version": "1"})
        except SourceError as e:
            if "401" in str(e) and attempt == 0:
                continue  # 令牌过期：重新获取一次
            raise
        if not data:
            return None
        if not data.get("success"):
            if data.get("code") in (401, 403) and attempt == 0:
                continue
            if data.get("code") in (404, 614):
                return None
            raise SourceError("ymgal", data.get("msg") or f"返回码 {data.get('code')}")
        return data.get("data")
    raise SourceError("ymgal", "认证失败")


def _ymgal_item(d: dict[str, Any], gid: Any) -> dict[str, Any]:
    return {
        "source": "ymgal", "sid": str(gid), "title": d.get("chineseName") or d.get("name"),
        "title_cn": d.get("chineseName") or None, "original": d.get("name") or None,
        "date": _date(d.get("releaseDate")), "developer": d.get("orgName") or None, "cover": d.get("mainImg") or None,
        "score": None, "nsfw": bool(d.get("restricted")), "url": f"https://www.ymgal.games/ga{gid}",
    }


def ymgal_search(q: str, limit: int = 10) -> list[dict[str, Any]]:
    data = _ymgal("/open/archive/search-game", {"mode": "list", "keyword": q[:95], "pageNum": 1,
                                                 "pageSize": min(limit, 20)}) or {}
    return [_ymgal_item(d, d.get("id")) for d in data.get("result") or [] if d.get("id")]


def ymgal_detail(sid: str, characters: bool = True) -> dict[str, Any] | None:
    data = _ymgal("/open/archive", {"gid": int(sid)})
    if not data or not data.get("game"):
        return None
    g = data["game"]
    out = _ymgal_item(g, g.get("gid") or sid)
    if g.get("developerId"):
        try:
            org = (_ymgal("/open/archive", {"orgId": g["developerId"]}) or {}).get("org") or {}
            out["developer"] = org.get("chineseName") or org.get("name") or None
        except SourceError:
            pass
    rels = g.get("releases") or []
    out.update({
        "aliases": _dedupe([x.get("name") for x in g.get("extensionName") or []]
                           + ([g["name"]] if g.get("chineseName") and g.get("name") else [])),
        "description": _clean(g.get("introduction")), "tags": _dedupe([g.get("typeDesc")] if g.get("typeDesc") else []),
        "platforms": _dedupe([r.get("platform") for r in rels if r.get("platform")]),
        "rank": None, "votes": None, "length_minutes": None, "has_chinese": g.get("haveChinese"),
        "links": [{"title": "月幕 Galgame", "url": out["url"]}]
        + [{"title": w.get("title") or "链接", "url": w.get("link")} for w in g.get("website") or []
           if (w.get("link") or "").startswith("http")][:6],
        "characters": [],
    })
    if characters:
        cmap, pmap = data.get("cidMapping") or {}, data.get("pidMapping") or {}
        for rel in g.get("characters") or []:
            c = cmap.get(str(rel.get("cid"))) or {}
            if not c.get("name"):
                continue
            cvp = pmap.get(str(rel.get("cvId"))) or {}
            out["characters"].append({
                "name": c.get("name"), "original": None, "role": "main" if rel.get("characterPosition") == 1 else "side",
                "image": c.get("mainImg") or None, "cv": cvp.get("name"), "description": None,
                "url": f"https://www.ymgal.games/ca{rel.get('cid')}",
            })
        out["characters"].sort(key=lambda c: c["role"] != "main")
    return out


def search(source: str, q: str, token: str | None = None) -> list[dict[str, Any]]:
    if source == "bangumi":
        return bangumi_search(q, token)
    if source == "vndb":
        return vndb_search(q)
    if source == "ymgal":
        return ymgal_search(q)
    raise SourceError(source, "未知来源")


def detail(source: str, sid: str, token: str | None = None, characters: bool = True) -> dict[str, Any] | None:
    try:
        if source == "bangumi":
            return bangumi_detail(sid, token, characters)
        if source == "vndb":
            return vndb_detail(sid, characters)
        if source == "ymgal":
            return ymgal_detail(sid, characters)
    except ValueError as e:
        raise SourceError(source, f"id 格式不对：{sid}") from e
    raise SourceError(source, "未知来源")
