"""收藏集：内容排序、追加 / 移除、封面、收藏集之间的排序。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..crud import get_or_404, make_crud_router, set_collection_items
from ..db import get_session


def _validate(session: Session, data: dict[str, Any]) -> None:
    cover = data.get("cover_asset_id")
    if cover is not None and session.get(m.Asset, cover) is None:
        raise HTTPException(422, f"封面素材 {cover} 不存在")


crud = make_crud_router(
    prefix="/api/collections", model=m.Collection, create_schema=s.CollectionCreate,
    update_schema=s.CollectionUpdate, read_schema=s.CollectionRead, tag_name="收藏集",
    order_by=(m.Collection.position, m.Collection.id), validate=_validate,
)
extra = APIRouter(prefix="/api/collections", tags=["收藏集"])


class IdList(BaseModel):
    asset_ids: list[int]


class CollectionOrder(BaseModel):
    collection_ids: list[int]


def _current(c: m.Collection) -> list[int]:
    return [a.id for a in c.assets]


def _reload(session: Session, c: m.Collection) -> m.Collection:
    session.commit()
    session.expire(c)
    return session.get(m.Collection, c.id)


@extra.put("/order", status_code=204)
def order_collections(body: CollectionOrder, session: Session = Depends(get_session)) -> None:
    """调整收藏集之间的顺序。"""
    for pos, cid in enumerate(body.collection_ids):
        c = get_or_404(session, m.Collection, cid)
        c.position = pos
    session.commit()


@extra.post("/{collection_id}/items", response_model=s.CollectionRead)
def add_items(collection_id: int, body: IdList, session: Session = Depends(get_session)) -> Any:
    """追加素材到末尾，已在收藏集中的会被忽略。"""
    c = get_or_404(session, m.Collection, collection_id)
    cur = _current(c)
    set_collection_items(session, c.id, cur + [i for i in body.asset_ids if i not in cur])
    return _reload(session, c)


@extra.delete("/{collection_id}/items/{asset_id}", response_model=s.CollectionRead)
def remove_item(collection_id: int, asset_id: int, session: Session = Depends(get_session)) -> Any:
    c = get_or_404(session, m.Collection, collection_id)
    set_collection_items(session, c.id, [i for i in _current(c) if i != asset_id])
    if c.cover_asset_id == asset_id:
        c.cover_asset_id = None
    return _reload(session, c)


@extra.put("/{collection_id}/order", response_model=s.CollectionRead)
def reorder(collection_id: int, body: IdList, session: Session = Depends(get_session)) -> Any:
    """按给定顺序重排；没列出的项保持原相对顺序排在后面。不能借此加入新素材。"""
    c = get_or_404(session, m.Collection, collection_id)
    cur = _current(c)
    unknown = [i for i in body.asset_ids if i not in cur]
    if unknown:
        raise HTTPException(422, f"这些素材不在收藏集中: {unknown}")
    ordered = list(dict.fromkeys(body.asset_ids))
    set_collection_items(session, c.id, ordered + [i for i in cur if i not in ordered])
    return _reload(session, c)
