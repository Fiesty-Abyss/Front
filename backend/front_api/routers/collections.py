"""收藏集：内容排序、追加 / 移除、封面、收藏集之间的排序。"""

from __future__ import annotations

from typing import Any

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..crud import get_or_404, make_crud_router, set_collection_items
from ..db import get_session
from .. import collectionpages as pages


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
    expected_revision: int | None = Field(default=None, ge=0)


class CollectionOrder(BaseModel):
    collection_ids: list[int]


class MemberWrite(BaseModel):
    expected_revision: int = Field(ge=0)
    asset_ids: list[int] = Field(min_length=1, max_length=1000)


class WindowOrder(MemberWrite):
    asset_ids: list[int] = Field(min_length=1, max_length=200)
    first_asset_id: int


class BatchEdit(MemberWrite):
    favorite: bool | None = None
    stars: int | None = Field(default=None, ge=0, le=5)
    preference: int | None = Field(default=None, ge=0, le=100)
    add_tag_ids: list[int] = Field(default=[], max_length=100)
    remove: bool = False

    @model_validator(mode='after')
    def operation(self):
        edits = self.favorite is not None or self.stars is not None or self.preference is not None or self.add_tag_ids
        if self.remove and edits:
            raise ValueError('移出和属性编辑请分开执行')
        if not self.remove and not edits:
            raise ValueError('请选择要修改的属性')
        return self


@extra.get('/summaries')
def summaries(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), session: Session = Depends(get_session)):
    total = session.scalar(select(func.count()).select_from(m.Collection))
    rows = session.execute(pages.summaries_query().order_by(m.Collection.position, m.Collection.id).offset(offset).limit(limit)).mappings().all()
    return {'items': [dict(row) for row in rows], 'total': total}


@extra.get('/{collection_id}/summary')
def collection_summary(collection_id: int, session: Session = Depends(get_session)):
    return pages.summary(session, pages.collection(session, collection_id))


@extra.patch('/{collection_id}/summary')
def update_summary(collection_id: int, body: s.CollectionUpdate, session: Session = Depends(get_session)):
    if 'asset_ids' in body.model_fields_set:
        raise HTTPException(422, '摘要接口不替换完整成员列表')
    pages.lock(session, collection_id)
    row = pages.collection(session, collection_id)
    data = body.model_dump(exclude_unset=True)
    _validate(session, data)
    for key, value in data.items():
        setattr(row, key, value)
    session.commit()
    return pages.summary(session, row)


@extra.get('/{collection_id}/members')
def members(collection_id: int, limit: int = Query(60, ge=1, le=200), cursor: str | None = Query(None, max_length=2048),
            q: str = '', kind: str = '', tag: list[int] = Query(default=[]),
            min_stars: int | None = Query(None, ge=0, le=5), min_preference: int | None = Query(None, ge=0, le=100),
            date_from: date | None = None, date_to: date | None = None, session: Session = Depends(get_session)):
    return pages.page(session, collection_id, dict(q=q, kind=kind, tag=sorted(set(tag)), min_stars=min_stars,
        min_preference=min_preference, date_from=date_from, date_to=date_to), limit, cursor)


def _finish_page_write(session, collection_id):
    session.commit()
    return pages.summary(session, pages.collection(session, collection_id))


@extra.post('/{collection_id}/members')
def append_members(collection_id: int, body: MemberWrite, session: Session = Depends(get_session)):
    pages.lock(session, collection_id, body.expected_revision)
    pages.append(session, collection_id, body.asset_ids)
    return _finish_page_write(session, collection_id)


@extra.put('/{collection_id}/members/order')
def order_members(collection_id: int, body: WindowOrder, session: Session = Depends(get_session)):
    pages.lock(session, collection_id, body.expected_revision)
    pages.reorder_window(session, collection_id, body.first_asset_id, body.asset_ids)
    return _finish_page_write(session, collection_id)


@extra.patch('/{collection_id}/members/batch')
def edit_members(collection_id: int, body: BatchEdit, session: Session = Depends(get_session)):
    pages.lock(session, collection_id, body.expected_revision)
    pages.batch(session, collection_id, body)
    return _finish_page_write(session, collection_id)


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
    pages.lock(session, collection_id, body.expected_revision)
    c = get_or_404(session, m.Collection, collection_id)
    cur = _current(c)
    set_collection_items(session, c.id, cur + [i for i in body.asset_ids if i not in cur])
    return _reload(session, c)


@extra.delete("/{collection_id}/items/{asset_id}", response_model=s.CollectionRead)
def remove_item(collection_id: int, asset_id: int, session: Session = Depends(get_session)) -> Any:
    pages.lock(session, collection_id)
    c = get_or_404(session, m.Collection, collection_id)
    set_collection_items(session, c.id, [i for i in _current(c) if i != asset_id])
    if c.cover_asset_id == asset_id:
        c.cover_asset_id = None
    return _reload(session, c)


@extra.put("/{collection_id}/order", response_model=s.CollectionRead)
def reorder(collection_id: int, body: IdList, session: Session = Depends(get_session)) -> Any:
    """按给定顺序重排；没列出的项保持原相对顺序排在后面。不能借此加入新素材。"""
    pages.lock(session, collection_id, body.expected_revision)
    c = get_or_404(session, m.Collection, collection_id)
    cur = _current(c)
    unknown = [i for i in body.asset_ids if i not in cur]
    if unknown:
        raise HTTPException(422, f"这些素材不在收藏集中: {unknown}")
    ordered = list(dict.fromkeys(body.asset_ids))
    set_collection_items(session, c.id, ordered + [i for i in cur if i not in ordered])
    return _reload(session, c)
