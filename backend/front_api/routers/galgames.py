"""galgame 游戏库：游玩状态、评分、游玩时长、笔记；元数据从 Bangumi / VNDB / 月幕 拉取（混合模式可互相补全），
可一键建立作品（CG 档案挂在作品下）、把来源里的角色导入角色百科。

设计参考了 ReinaManager（AGPL-3.0）与恋页 KoiPage（未指定许可证）的思路：多来源元数据、用户改过的字段优先、
状态筛选、批量添加、NSFW 封面模糊、手动游玩记录与时长日历、分享足迹。这里没有使用它们的任何代码。
"""

from __future__ import annotations

import io
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..config import get_settings
from ..crud import get_or_404, make_crud_router, qp
from ..db import get_session
from ..filetypes.util import is_image
from ..galgame import meta
from ..galgame import sources as src

STATUSES = ("unplayed", "wishlist", "playing", "finished", "shelved", "dropped")
META_FIELDS = ("title", "title_cn", "original", "aliases", "description", "developer", "release_date",
               "platforms", "source_tags", "nsfw")
IMAGE_HOSTS = ("bgm.tv", "vndb.org", "ymgal.games", "ymgal.com")
COVER_SIZE = (600, 860)
MAX_COVER = 12 * 1024 * 1024
SORTS = {
    "updated": (m.Galgame.updated_at.desc(),),
    "added": (m.Galgame.created_at.desc(),),
    "title": (m.Galgame.title.asc(),),
    "release": (m.Galgame.release_date.is_(None), m.Galgame.release_date.desc()),
    "rating": (m.Galgame.my_rating.is_(None), m.Galgame.my_rating.desc()),
    "playtime": (m.Galgame.play_minutes.desc(),),
}


def _filters(stmt: Any, request: Request) -> Any:
    if st := qp(request, "status"):
        stmt = stmt.where(m.Galgame.status == st)
    if source := qp(request, "source"):
        if source == "none":
            stmt = stmt.where(func.json_type(m.Galgame.sources, "$.bangumi").is_(None),
                              func.json_type(m.Galgame.sources, "$.vndb").is_(None),
                              func.json_type(m.Galgame.sources, "$.ymgal").is_(None))
        elif source in src.SOURCES:
            stmt = stmt.where(func.json_type(m.Galgame.sources, f"$.{source}").is_not(None))
    if (nsfw := qp(request, "nsfw")) in ("0", "1"):
        stmt = stmt.where(m.Galgame.nsfw.is_(nsfw == "1"))
    if work := qp(request, "work_id"):
        stmt = stmt.where(m.Galgame.work_id == int(work))
    if dev := qp(request, "developer"):
        stmt = stmt.where(m.Galgame.developer == dev)
    sort = SORTS.get(qp(request, "sort") or "updated", SORTS["updated"])
    return stmt.order_by(m.Galgame.pinned.desc(), *sort)


def _validate(session: Session, data: dict[str, Any]) -> None:
    if data.get("work_id") is not None:
        get_or_404(session, m.Work, data["work_id"])


def _trim(d: dict[str, Any]) -> dict[str, Any]:
    d["characters"] = None
    d["description"] = (d.get("description") or "")[:160] or None
    d["notes"] = None
    return d


crud = make_crud_router(
    prefix="/api/galgames", model=m.Galgame, create_schema=s.GalgameCreate, update_schema=s.GalgameUpdate,
    read_schema=s.GalgameRead, tag_name="游戏库", filters=_filters, validate=_validate, list_trim=_trim,
    order_by=(m.Galgame.id.desc(),),
)
extra = APIRouter(prefix="/api/galgames", tags=["游戏库"])


# 用户手动修改元数据字段时记进 overrides，之后“刷新元数据”不会覆盖它们
@event.listens_for(m.Galgame, "before_update")
def _track_overrides(_mapper: Any, _conn: Any, target: m.Galgame) -> None:
    if getattr(target, "_meta_write", False):
        return
    from sqlalchemy import inspect as sa_inspect

    state = sa_inspect(target)
    changed = [f for f in META_FIELDS if state.attrs[f].history.has_changes()]
    if changed:
        target.overrides = sorted(set(target.overrides or []) | set(changed))


def _cover_path(gid: int):
    return get_settings().thumb_dir / f"galgame-{gid}.webp"


@event.listens_for(m.Galgame, "after_delete")
def _drop_cover(_mapper: Any, _conn: Any, target: m.Galgame) -> None:
    _cover_path(target.id).unlink(missing_ok=True)


# ------------------------------------------------------------------ 设置
class GalSettings(BaseModel):
    mode: str | None = Field(default=None, pattern="^(mixed|bangumi|vndb|ymgal)$")
    order: list[str] | None = None
    enabled: dict[str, bool] | None = None
    bangumi_token: str | None = Field(default=None, max_length=200)
    fetch_characters: bool | None = None
    blur_nsfw: bool | None = None
    auto_match: bool | None = None


@extra.get("/meta/settings")
def get_meta_settings(session: Session = Depends(get_session)) -> dict[str, Any]:
    return meta.public_settings(meta.load_settings(session))


@extra.put("/meta/settings")
def put_meta_settings(payload: GalSettings, session: Session = Depends(get_session)) -> dict[str, Any]:
    cfg = meta.load_settings(session)
    data = payload.model_dump(exclude_none=True)
    if "order" in data:
        bad = [x for x in data["order"] if x not in src.SOURCES]
        if bad or len(set(data["order"])) != len(data["order"]):
            raise HTTPException(422, f"来源顺序不对：{data['order']}")
    if "enabled" in data:
        data["enabled"] = {k: v for k, v in data["enabled"].items() if k in src.SOURCES}
    cfg.update(data)
    if not any(cfg["enabled"].get(x) for x in src.SOURCES):
        raise HTTPException(422, "至少启用一个来源")
    row = session.get(m.AppSetting, meta.KEY)
    if row:
        row.value = cfg
    else:
        session.add(m.AppSetting(key=meta.KEY, value=cfg))
    session.commit()
    return meta.public_settings(cfg)


# ------------------------------------------------------------------ 元数据
@extra.get("/meta/search")
def meta_search(q: str = Query(min_length=1, max_length=95), source: str | None = None,
                session: Session = Depends(get_session)) -> dict[str, Any]:
    if source and source not in src.SOURCES:
        raise HTTPException(422, "未知来源")
    cfg = meta.load_settings(session)
    out = meta.search(q.strip(), cfg, source)
    # 已经在库里的条目做个标记
    have: dict[tuple[str, str], int] = {}
    for gid, sources in session.execute(select(m.Galgame.id, m.Galgame.sources)).all():
        for k, v in (sources or {}).items():
            if isinstance(v, dict) and v.get("id"):
                have[(k, str(v["id"]))] = gid
    for k, r in out["results"].items():
        for it in r["items"]:
            it["in_library"] = have.get((k, str(it["sid"])))
    return out


class Picks(BaseModel):
    picks: dict[str, str] = Field(min_length=1)
    auto_match: bool | None = None


@extra.post("/meta/preview")
def meta_preview(payload: Picks, session: Session = Depends(get_session)) -> dict[str, Any]:
    cfg = meta.load_settings(session)
    r = meta.fetch(payload.picks, cfg, payload.auto_match)
    if not r["details"]:
        raise HTTPException(502, "；".join(r["errors"].values()) or "没有拿到任何元数据")
    return r


def _apply_meta(g: m.Galgame, merged: dict[str, Any], keep_overrides: bool = True) -> None:
    locked = set(g.overrides or []) if keep_overrides else set()
    g._meta_write = True  # type: ignore[attr-defined]
    for f in META_FIELDS:
        if f in merged and f not in locked and merged[f] not in (None, "", []):
            setattr(g, f, merged[f][:300] if isinstance(merged[f], str) and f in ("title", "title_cn", "original", "developer") else merged[f])
    if merged.get("cover_url"):
        g.cover_url = merged["cover_url"]
    if merged.get("characters"):
        g.characters = merged["characters"]
    if merged.get("links"):
        g.links = merged["links"]
    g.sources = {**(g.sources or {}), **(merged.get("sources") or {})}
    if not keep_overrides:
        g.overrides = []


def _allowed_image_host(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    host = parts.hostname.lower()
    mock_hosts = {urlsplit(src.base(x)).hostname for x in src.SOURCES}
    return host in mock_hosts or any(host == h or host.endswith("." + h) for h in IMAGE_HOSTS)


def _store_cover(g: m.Galgame, data: bytes) -> None:
    if len(data) > MAX_COVER or not is_image(data):
        raise HTTPException(422, "不是可用的图片")
    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
        img.thumbnail(COVER_SIZE)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, "图片无法解码") from e
    path = _cover_path(g.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "WEBP", quality=86)
    g._meta_write = True  # type: ignore[attr-defined]
    g.has_cover = True


def _download_cover(g: m.Galgame) -> str | None:
    """把封面存到本地（只在用户添加 / 点“保存封面”时调用）。返回错误信息或 None。"""
    url = g.cover_url
    if not url:
        return "没有封面地址"
    if not _allowed_image_host(url):
        return "封面不在已知的元数据图床上，未下载"
    try:
        with src.client_factory() as c:
            r = c.get(url, headers={"User-Agent": src.USER_AGENT})
        if r.status_code >= 400:
            return f"封面下载失败（HTTP {r.status_code}）"
        _store_cover(g, r.content)
    except HTTPException as e:
        return str(e.detail)
    except Exception as e:  # noqa: BLE001
        return f"封面下载失败（{type(e).__name__}）"
    return None


class AddFromMeta(BaseModel):
    picks: dict[str, str] = Field(min_length=1)
    auto_match: bool | None = None
    status: s.GalStatus = "wishlist"
    work: str | int | None = "new"  # "new" 新建作品 / 作品 id / None 不关联
    save_cover: bool = True
    import_characters: bool = False


def _make_work(session: Session, g: m.Galgame) -> m.Work:
    year = int(g.release_date[:4]) if g.release_date and g.release_date[:4].isdigit() else None
    w = m.Work(title=g.title, kind="galgame", year=year, publisher=g.developer,
               url=next((ln["url"] for ln in g.links or [] if ln.get("title") == "官方网站"), None),
               description=(g.description or "")[:2000] or None)
    session.add(w)
    session.flush()
    return w


@extra.post("/from-meta", response_model=s.GalgameRead, status_code=201)
def add_from_meta(payload: AddFromMeta, session: Session = Depends(get_session)) -> Any:
    cfg = meta.load_settings(session)
    r = meta.fetch(payload.picks, cfg, payload.auto_match)
    merged = r["merged"]
    if not merged:
        raise HTTPException(502, "；".join(r["errors"].values()) or "没有拿到任何元数据")
    g = m.Galgame(title=merged["title"] or "未命名", status=payload.status)
    _apply_meta(g, merged, keep_overrides=False)
    session.add(g)
    session.flush()
    if payload.work == "new":
        g.work_id = _make_work(session, g).id
    elif payload.work not in (None, "", "none"):
        g.work_id = get_or_404(session, m.Work, int(payload.work)).id
    if payload.save_cover:
        _download_cover(g)
    if payload.import_characters and g.work_id:
        _import_characters(session, g, None)
    session.commit()
    session.refresh(g)
    return g


class QuickAdd(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    status: s.GalStatus = "wishlist"
    work: str | None = "new"
    save_cover: bool = True
    accept_first: bool = False  # 一键模式：不看相似度，直接用排在最前的来源的第一条结果


@extra.post("/quick-add", status_code=201)
def quick_add(payload: QuickAdd, session: Session = Depends(get_session)) -> dict[str, Any]:
    """批量添加用：按来源顺序找最像的一条；找不到就只建一个只有标题的条目（之后可以手动匹配）。"""
    cfg = meta.load_settings(session)
    title = payload.title.strip()
    found = meta.search(title, {**cfg, "mode": cfg["mode"] if cfg["mode"] != "mixed" else cfg["order"][0]})
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for source in found["order"]:
        for it in found["results"].get(source, {}).get("items", [])[:5]:
            sc = meta.best_score([title], it)
            if sc > best[0]:
                best = (sc, it)
    errors = [r["error"] for r in found["results"].values() if r.get("error")]
    if payload.accept_first:
        first = next((it for so in found["order"] for it in found["results"].get(so, {}).get("items", [])[:1]), None)
        if first:
            best = (meta.best_score([title], first), first)
    if best[1] and (best[0] >= 0.6 or payload.accept_first):
        dup = next((gid for gid, so in session.execute(select(m.Galgame.id, m.Galgame.sources)).all()
                    if str(((so or {}).get(best[1]["source"]) or {}).get("id")) == str(best[1]["sid"])), None)
        if dup:
            return {"status": "exists", "id": dup, "title": best[1]["title"]}
        g = add_from_meta(AddFromMeta(picks={best[1]["source"]: best[1]["sid"]}, status=payload.status,
                                      work=payload.work, save_cover=payload.save_cover), session)
        return {"status": "matched", "id": g.id, "title": g.title, "score": round(best[0], 2),
                "source": best[1]["source"], "errors": errors}
    g = m.Galgame(title=title, status=payload.status)
    session.add(g)
    session.commit()
    return {"status": "unmatched", "id": g.id, "title": title, "errors": errors}


class Refresh(BaseModel):
    sources: list[str] | None = None
    reset_overrides: bool = False
    save_cover: bool = False


@extra.post("/{gid}/refresh", response_model=s.GalgameRead)
def refresh(gid: int, payload: Refresh = Body(default_factory=Refresh), session: Session = Depends(get_session)) -> Any:
    g = get_or_404(session, m.Galgame, gid)
    picks = {k: str(v["id"]) for k, v in (g.sources or {}).items()
             if isinstance(v, dict) and v.get("id") and (not payload.sources or k in payload.sources)}
    if not picks:
        raise HTTPException(422, "这个条目还没有关联任何来源，先“匹配元数据”")
    cfg = meta.load_settings(session)
    r = meta.fetch(picks, cfg, match=False)
    if not r["details"]:
        raise HTTPException(502, "；".join(r["errors"].values()) or "没有拿到任何元数据")
    _apply_meta(g, r["merged"], keep_overrides=not payload.reset_overrides)
    if payload.save_cover:
        _download_cover(g)
    session.commit()
    session.refresh(g)
    return g


class Match(BaseModel):
    source: s.GalSource
    sid: str = Field(min_length=1, max_length=40)
    save_cover: bool = False


@extra.post("/{gid}/match", response_model=s.GalgameRead)
def match(gid: int, payload: Match, session: Session = Depends(get_session)) -> Any:
    """手动关联（或换成）某个来源的条目，并合并它的元数据。"""
    g = get_or_404(session, m.Galgame, gid)
    cfg = meta.load_settings(session)
    r = meta.fetch({payload.source: payload.sid}, cfg, match=False)
    if payload.source not in r["details"]:
        raise HTTPException(502, r["errors"].get(payload.source) or "没有拿到元数据")
    order = [payload.source] + [x for x in cfg["order"] if x != payload.source]
    others = {k: v for k, v in (g.sources or {}).items() if k != payload.source}
    g.sources = others
    _apply_meta(g, meta.merge(r["details"], order))
    if payload.save_cover or not g.has_cover:
        _download_cover(g)
    session.commit()
    session.refresh(g)
    return g


@extra.delete("/{gid}/sources/{source}", response_model=s.GalgameRead)
def unlink(gid: int, source: str, session: Session = Depends(get_session)) -> Any:
    g = get_or_404(session, m.Galgame, gid)
    g._meta_write = True  # type: ignore[attr-defined]
    g.sources = {k: v for k, v in (g.sources or {}).items() if k != source}
    session.commit()
    session.refresh(g)
    return g


# ------------------------------------------------------------------ 封面
@extra.get("/{gid}/cover")
def get_cover(gid: int, session: Session = Depends(get_session)) -> FileResponse:
    get_or_404(session, m.Galgame, gid)
    path = _cover_path(gid)
    if not path.exists():
        raise HTTPException(404, "没有本地封面")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "no-cache"})


@extra.post("/{gid}/cover", response_model=s.GalgameRead)
def save_cover(gid: int, session: Session = Depends(get_session)) -> Any:
    """从来源的封面地址下载到本地。"""
    g = get_or_404(session, m.Galgame, gid)
    err = _download_cover(g)
    if err:
        raise HTTPException(502, err)
    session.commit()
    session.refresh(g)
    return g


@extra.put("/{gid}/cover", response_model=s.GalgameRead)
async def upload_cover(gid: int, file: UploadFile = File(...), session: Session = Depends(get_session)) -> Any:
    g = get_or_404(session, m.Galgame, gid)
    _store_cover(g, await file.read(MAX_COVER + 1))
    session.commit()
    session.refresh(g)
    return g


@extra.delete("/{gid}/cover", response_model=s.GalgameRead)
def delete_cover(gid: int, session: Session = Depends(get_session)) -> Any:
    g = get_or_404(session, m.Galgame, gid)
    _cover_path(gid).unlink(missing_ok=True)
    g._meta_write = True  # type: ignore[attr-defined]
    g.has_cover = False
    session.commit()
    session.refresh(g)
    return g


# ------------------------------------------------------------------ 作品与角色
@extra.post("/{gid}/work", response_model=s.GalgameRead)
def create_work(gid: int, session: Session = Depends(get_session)) -> Any:
    g = get_or_404(session, m.Galgame, gid)
    if g.work_id and session.get(m.Work, g.work_id):
        raise HTTPException(409, "已经关联了作品")
    g.work_id = _make_work(session, g).id
    session.commit()
    session.refresh(g)
    return g


def _import_characters(session: Session, g: m.Galgame, indexes: list[int] | None) -> dict[str, Any]:
    chars = g.characters or []
    picked = [(i, chars[i]) for i in (indexes if indexes is not None else range(len(chars))) if 0 <= i < len(chars)]
    existing = {c.name: c for c in session.scalars(select(m.Character).where(m.Character.work_id == g.work_id))}
    created, skipped = [], []
    for _i, c in picked:
        name = (c.get("name") or "").strip()[:200]
        if not name:
            continue
        if name in existing:
            skipped.append(existing[name].id)
            continue
        profile = "\n".join(x for x in [
            f"- 配音：{c['cv']}" if c.get("cv") else "", f"- 资料：{c['url']}" if c.get("url") else ""] if x) or None
        ch = m.Character(name=name, alias=(c.get("original") or None), work_id=g.work_id,
                         summary=(c.get("description") or None) and c["description"][:1000], profile=profile)
        session.add(ch)
        session.flush()
        session.add(m.Appearance(character_id=ch.id, work_id=g.work_id, role="主角" if c.get("role") == "main" else "配角"))
        existing[name] = ch
        created.append(ch.id)
    return {"created": created, "skipped": skipped}


class ImportChars(BaseModel):
    indexes: list[int] | None = None


@extra.post("/{gid}/import-characters")
def import_characters(gid: int, payload: ImportChars = Body(default_factory=ImportChars),
                      session: Session = Depends(get_session)) -> dict[str, Any]:
    g = get_or_404(session, m.Galgame, gid)
    if not g.work_id:
        g.work_id = _make_work(session, g).id
    out = _import_characters(session, g, payload.indexes)
    session.commit()
    return {**out, "work_id": g.work_id}


@extra.get("/stats/summary")
def stats(session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = session.execute(select(m.Galgame.status, func.count(), func.coalesce(func.sum(m.Galgame.play_minutes), 0))
                           .group_by(m.Galgame.status)).all()
    by = {st: {"count": 0, "minutes": 0} for st in STATUSES}
    for st, n, mins in rows:
        by.setdefault(st, {"count": 0, "minutes": 0}).update(count=n, minutes=int(mins))
    devs = session.execute(select(m.Galgame.developer, func.count()).where(m.Galgame.developer.is_not(None))
                           .group_by(m.Galgame.developer).order_by(func.count().desc()).limit(12)).all()
    return {"total": sum(v["count"] for v in by.values()), "minutes": sum(v["minutes"] for v in by.values()),
            "by_status": by, "developers": [{"name": d, "count": n} for d, n in devs],
            "rated": session.scalar(select(func.avg(m.Galgame.my_rating)).where(m.Galgame.my_rating.is_not(None)))}


@extra.get("/{gid}/cg")
def cg_summary(gid: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """关联作品下的 CG 档案概览（详情页用）。"""
    g = get_or_404(session, m.Galgame, gid)
    if not g.work_id:
        return {"work_id": None, "count": 0, "items": []}
    stmt = select(m.Asset).where(m.Asset.work_id == g.work_id).order_by(m.Asset.id)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = [{"id": a.id, "title": a.title, "kind": a.kind} for a in session.scalars(stmt.limit(12))]
    return {"work_id": g.work_id, "count": total, "items": items}



# ------------------------------------------------------------------ 游玩记录
class PlayIn(BaseModel):
    played_on: s.DateStr
    minutes: int = Field(ge=1, le=24 * 60)
    note: str | None = Field(default=None, max_length=500)


def _play_dict(p: m.GalgamePlay, title: str | None = None) -> dict[str, Any]:
    d = {"id": p.id, "galgame_id": p.galgame_id, "played_on": p.played_on, "minutes": p.minutes, "note": p.note}
    if title is not None:
        d["title"] = title
    return d


@extra.get("/plays/summary")
def plays_summary(days: int = Query(default=120, ge=7, le=800), session: Session = Depends(get_session)) -> dict[str, Any]:
    """首页 / 游戏库用：每天的时长（日历）、今天 / 本周 / 本月合计、最近记录。日期按本地日期。"""
    from datetime import date, timedelta

    today = date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    rows = session.execute(select(m.GalgamePlay.played_on, func.sum(m.GalgamePlay.minutes))
                           .where(m.GalgamePlay.played_on >= start).group_by(m.GalgamePlay.played_on)).all()
    by_day = {d: int(n) for d, n in rows}
    week0 = (today - timedelta(days=today.weekday())).isoformat()
    month0 = today.replace(day=1).isoformat()
    recent = session.execute(select(m.GalgamePlay, m.Galgame.title).join(m.Galgame, m.Galgame.id == m.GalgamePlay.galgame_id)
                             .order_by(m.GalgamePlay.played_on.desc(), m.GalgamePlay.id.desc()).limit(12)).all()
    return {
        "today": by_day.get(today.isoformat(), 0),
        "week": sum(v for k, v in by_day.items() if k >= week0),
        "month": sum(v for k, v in by_day.items() if k >= month0),
        "by_day": by_day, "start": start, "end": today.isoformat(),
        "recent": [_play_dict(p, t) for p, t in recent],
    }


@extra.get("/{gid}/plays")
def list_plays(gid: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    get_or_404(session, m.Galgame, gid)
    rows = session.scalars(select(m.GalgamePlay).where(m.GalgamePlay.galgame_id == gid)
                           .order_by(m.GalgamePlay.played_on.desc(), m.GalgamePlay.id.desc()))
    return [_play_dict(p) for p in rows]


@extra.post("/{gid}/plays", status_code=201)
def add_play(gid: int, payload: PlayIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    g = get_or_404(session, m.Galgame, gid)
    p = m.GalgamePlay(galgame_id=gid, played_on=payload.played_on, minutes=payload.minutes, note=payload.note or None)
    session.add(p)
    g.play_minutes = (g.play_minutes or 0) + payload.minutes
    if g.status in ("unplayed", "wishlist"):
        g.status = "playing"
    if not g.started_on or g.started_on > payload.played_on:
        g.started_on = payload.played_on
    session.commit()
    return {**_play_dict(p), "play_minutes": g.play_minutes, "status": g.status}


@extra.delete("/plays/{pid}", status_code=204)
def delete_play(pid: int, session: Session = Depends(get_session)) -> Response:
    p = get_or_404(session, m.GalgamePlay, pid)
    g = session.get(m.Galgame, p.galgame_id)
    if g:
        g.play_minutes = max(0, (g.play_minutes or 0) - p.minutes)
    session.delete(p)
    session.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ 批量操作与导出
class Bulk(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)
    status: s.GalStatus | None = None
    pinned: bool | None = None
    delete: bool = False


@extra.post("/bulk")
def bulk(payload: Bulk, session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = session.scalars(select(m.Galgame).where(m.Galgame.id.in_(payload.ids))).all()
    for g in rows:
        if payload.delete:
            session.delete(g)
            continue
        if payload.status:
            g.status = payload.status
        if payload.pinned is not None:
            g.pinned = payload.pinned
    session.commit()
    return {"count": len(rows), "deleted": payload.delete}


EXPORT_FIELDS = ("id", "title", "title_cn", "original", "status", "my_rating", "play_minutes", "started_on", "finished_on",
                 "developer", "release_date", "platforms", "aliases", "nsfw", "work_id", "notes")


@extra.get("/export/file")
def export_library(format: str = Query(default="json", pattern="^(json|csv)$"), session: Session = Depends(get_session)) -> Response:
    """导出游戏库（不含封面图片）。CSV 用 UTF-8 BOM，Excel 可直接打开。"""
    import csv
    import json

    rows = session.scalars(select(m.Galgame).order_by(m.Galgame.id)).all()
    data = []
    for g in rows:
        d = {f: getattr(g, f) for f in EXPORT_FIELDS}
        d["sources"] = {k: v.get("id") for k, v in (g.sources or {}).items() if isinstance(v, dict)}
        d["tags"] = [t.name for t in g.tags]
        data.append(d)
    if format == "json":
        body = json.dumps({"format": "front-galgames", "version": 1, "items": data}, ensure_ascii=False, indent=2).encode()
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=front-galgames.json"})
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = [*EXPORT_FIELDS, "bangumi", "vndb", "ymgal", "tags"]
    w.writerow(cols)
    for d in data:
        row = []
        for c in cols:
            v = d["sources"].get(c) if c in src.SOURCES else d.get(c)
            row.append("、".join(v) if isinstance(v, list) else "" if v is None else v)
        w.writerow(row)
    return Response(("\ufeff" + buf.getvalue()).encode(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=front-galgames.csv"})
