"""浏览器查询：从角色 / 作品 / 模型一键打开各站点的搜索页。

只生成链接，在用户自己的浏览器里打开：Front 不抓取这些站点的页面，也不下载任何文件。
站点列表保存在 app_settings（键 quick_search_sites），可在“设置”里增删改。
URL 模板里的 {q} 会被替换为 URL 编码后的关键词；没有 {q} 的条目就是普通链接（例如官网）。
"""

from __future__ import annotations

import re
import uuid
from typing import Any
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_session

router = APIRouter(prefix="/api/quick-search", tags=["浏览器查询"])
KEY = "quick_search_sites"
KINDS = ("work", "character", "model", "world")

# 默认只放正规的资料站、百科与官方站点。
DEFAULT_SITES: list[dict[str, Any]] = [
    {"id": "bangumi-game", "name": "Bangumi 游戏", "url": "https://bgm.tv/subject_search/{q}?cat=4", "kinds": ["work"]},
    {"id": "bangumi-crt", "name": "Bangumi 角色", "url": "https://bgm.tv/mono_search/{q}?cat=crt", "kinds": ["character"]},
    {"id": "vndb", "name": "VNDB", "url": "https://vndb.org/v?q={q}", "kinds": ["work"]},
    {"id": "vndb-crt", "name": "VNDB 角色", "url": "https://vndb.org/c?q={q}", "kinds": ["character"]},
    {"id": "ymgal", "name": "月幕 Galgame", "url": "https://www.ymgal.games/search?type=ga&keyword={q}", "kinds": ["work"]},
    {"id": "2dfan", "name": "2DFan", "url": "https://2dfan.com/search?keyword={q}", "kinds": ["work", "character"]},
    {"id": "moegirl", "name": "萌娘百科", "url": "https://zh.moegirl.org.cn/index.php?search={q}", "kinds": ["work", "character", "world"]},
    {"id": "bilibili-2072586344", "name": "Bilibili 空间 2072586344", "url": "https://space.bilibili.com/2072586344/search?keyword={q}", "kinds": ["work", "character"]},
    {"id": "civitai", "name": "Civitai", "url": "https://civitai.com/search/models?query={q}", "kinds": ["model", "character"]},
    {"id": "summer-pockets", "name": "Summer Pockets 官网", "url": "https://summerpockets.com/", "kinds": ["work"],
     "match": ["Summer Pockets", "サマーポケッツ", "夏日口袋"]},
]
for _s in DEFAULT_SITES:
    _s.setdefault("enabled", True)
    _s.setdefault("match", [])


class Site(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10], max_length=64)
    name: str = Field(min_length=1, max_length=60)
    url: str = Field(min_length=8, max_length=500)
    kinds: list[str] = Field(default_factory=lambda: list(KINDS))
    enabled: bool = True
    match: list[str] = Field(default_factory=list, max_length=20)  # 非空时只在关键词包含其中之一时显示

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip()
        parts = urlsplit(v.replace("{q}", "x"))
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("只支持 http:// 或 https:// 开头的网址")
        return v

    @field_validator("kinds")
    @classmethod
    def _kinds(cls, v: list[str]) -> list[str]:
        bad = [k for k in v if k not in KINDS]
        if bad:
            raise ValueError(f"未知的类型：{bad}")
        return v or list(KINDS)


class SiteList(BaseModel):
    sites: list[Site] = Field(max_length=100)


def load(session: Session) -> list[dict[str, Any]]:
    row = session.get(m.AppSetting, KEY)
    return list(row.value) if row is not None and isinstance(row.value, list) else [dict(s) for s in DEFAULT_SITES]


def save(session: Session, sites: list[dict[str, Any]]) -> None:
    row = session.get(m.AppSetting, KEY)
    if row is None:
        session.add(m.AppSetting(key=KEY, value=sites))
    else:
        row.value = sites
    session.commit()


def build_url(template: str, q: str) -> str:
    return template.replace("{q}", quote(q.strip(), safe="")) if "{q}" in template else template


def links(sites: list[dict[str, Any]], kind: str | None, q: str) -> list[dict[str, Any]]:
    out = []
    low = q.casefold()
    for s in sites:
        if not s.get("enabled", True):
            continue
        if kind and kind not in (s.get("kinds") or KINDS):
            continue
        if s.get("match") and not any(t.casefold() in low for t in s["match"] if t):
            continue
        out.append({"id": s["id"], "name": s["name"], "url": build_url(s["url"], q), "search": "{q}" in s["url"],
                    "host": urlsplit(s["url"].replace("{q}", "x")).netloc})
    return out


@router.get("/sites")
def get_sites(session: Session = Depends(get_session)) -> dict[str, Any]:
    return {"sites": load(session), "kinds": list(KINDS)}


@router.put("/sites")
def put_sites(body: SiteList, session: Session = Depends(get_session)) -> dict[str, Any]:
    ids = [s.id for s in body.sites]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "站点 id 重复")
    save(session, [s.model_dump() for s in body.sites])
    return get_sites(session)


@router.post("/sites/reset")
def reset_sites(session: Session = Depends(get_session)) -> dict[str, Any]:
    save(session, [dict(s) for s in DEFAULT_SITES])
    return get_sites(session)


@router.get("")
def quick_links(q: str, kind: str | None = None, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    q = re.sub(r"\s+", " ", q).strip()
    if not q:
        raise HTTPException(422, "关键词不能为空")
    if kind and kind not in KINDS:
        raise HTTPException(422, f"kind 只能是 {KINDS}")
    return links(load(session), kind, q)
