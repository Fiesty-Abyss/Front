"""通用 CRUD 路由工厂：列表（分页/标签/全文检索/自定义筛选）、详情、新增、修改、删除。"""


from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from . import models as m
from .db import get_session
from .search import SPEC, matching_ids

FilterFn = Callable[[Select, Request], Select]


def get_or_404(session: Session, model: type, obj_id: int) -> Any:
    obj = session.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {obj_id} 不存在")
    return obj


def resolve_tags(session: Session, tag_ids: list[int]) -> list[m.Tag]:
    if not tag_ids:
        return []
    tags = session.scalars(select(m.Tag).where(m.Tag.id.in_(tag_ids))).all()
    missing = set(tag_ids) - {t.id for t in tags}
    if missing:
        raise HTTPException(422, f"标签不存在: {sorted(missing)}")
    return list(tags)


def set_collection_items(session: Session, collection_id: int, asset_ids: list[int]) -> None:
    """按给定顺序写入收藏集内容（position 从 0 开始）。重复 id 只保留第一次出现。"""
    ordered = list(dict.fromkeys(asset_ids))
    found = set(session.scalars(select(m.Asset.id).where(m.Asset.id.in_(ordered))).all())
    missing = [i for i in ordered if i not in found]
    if missing:
        raise HTTPException(422, f"素材不存在: {missing}")
    session.execute(m.collection_assets.delete().where(m.collection_assets.c.collection_id == collection_id))
    if ordered:
        session.execute(
            m.collection_assets.insert(),
            [{"collection_id": collection_id, "asset_id": a, "position": i} for i, a in enumerate(ordered)],
        )


def apply_payload(session: Session, obj: Any, data: dict[str, Any]) -> list[int] | None:
    """写入字段与标签；返回待写入的 asset_ids（需要在 flush 之后处理）。"""
    tag_ids = data.pop("tag_ids", None)
    asset_ids = data.pop("asset_ids", None)
    for key, value in data.items():
        setattr(obj, key, value)
    if tag_ids is not None:
        obj.tags = resolve_tags(session, tag_ids)
    return asset_ids


def _finish(session: Session, obj: Any, asset_ids: list[int] | None) -> None:
    session.flush()
    if asset_ids is not None:
        set_collection_items(session, obj.id, asset_ids)
    session.commit()
    session.refresh(obj)
    if asset_ids is not None:
        session.expire(obj, ["assets"])


def make_crud_router(
    *,
    prefix: str,
    model: type,
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    read_schema: type[BaseModel],
    tag_name: str,
    filters: FilterFn | None = None,
    order_by: Any = None,
    validate: Callable[[Session, dict[str, Any]], None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag_name])
    entity = SPEC[model][0] if model in SPEC else None
    has_tags = hasattr(model, "tags")

    @router.get("", response_model=dict)
    def list_items(
        request: Request,
        q: str | None = None,
        tag: list[int] = Query(default=[]),
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        stmt = select(model)
        if q and entity:
            stmt = stmt.where(model.id.in_(matching_ids(session, entity, q)))
        if tag and has_tags:
            # 多个标签取交集：必须同时拥有全部所选标签
            for tag_id in tag:
                stmt = stmt.where(model.tags.any(m.Tag.id == tag_id))
        if filters:
            stmt = filters(stmt, request)
        total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        if order_by is None:
            stmt = stmt.order_by(model.id.desc())
        elif isinstance(order_by, tuple):
            stmt = stmt.order_by(*order_by)
        else:
            stmt = stmt.order_by(order_by)
        rows = session.scalars(stmt.limit(limit).offset(offset)).all()
        return {
            "items": [read_schema.model_validate(r).model_dump(mode="json") for r in rows],
            "total": total,
        }

    @router.get("/{obj_id}", response_model=read_schema)
    def get_item(obj_id: int, session: Session = Depends(get_session)) -> Any:
        return get_or_404(session, model, obj_id)

    @router.post("", response_model=read_schema, status_code=201)
    def create_item(payload: create_schema, session: Session = Depends(get_session)) -> Any:  # type: ignore[valid-type]
        data = payload.model_dump()  # type: ignore[attr-defined]
        if validate:
            validate(session, data)
        obj = model()
        asset_ids = apply_payload(session, obj, data)
        session.add(obj)
        _finish(session, obj, asset_ids)
        return obj

    @router.patch("/{obj_id}", response_model=read_schema)
    def update_item(obj_id: int, payload: update_schema, session: Session = Depends(get_session)) -> Any:  # type: ignore[valid-type]
        obj = get_or_404(session, model, obj_id)
        data = payload.model_dump(exclude_unset=True)  # type: ignore[attr-defined]
        if validate:
            validate(session, data)
        asset_ids = apply_payload(session, obj, data)
        _finish(session, obj, asset_ids)
        return obj

    @router.delete("/{obj_id}", status_code=204)
    def delete_item(obj_id: int, session: Session = Depends(get_session)) -> Response:
        obj = get_or_404(session, model, obj_id)
        session.delete(obj)
        session.commit()
        return Response(status_code=204)

    router.list_items = list_items  # type: ignore[attr-defined]
    return router


def qp(request: Request, name: str) -> str | None:
    value = request.query_params.get(name)
    return value if value not in (None, "") else None
