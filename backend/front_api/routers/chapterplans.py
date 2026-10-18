from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from .. import chapterplans, chapters, models as m
from ..crud import get_or_404
from ..db import get_session

router = APIRouter(prefix='/api/assets', tags=['章节整理'])


class Boundary(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(ge=0)
    body_start: StrictInt | None = Field(default=None, ge=0)


class PlanInput(BaseModel):
    text_hash: str = Field(min_length=64, max_length=64)
    base_revision: int = Field(default=0, ge=0)
    chapters: list[Boundary] = Field(min_length=1, max_length=5000)
    note: str = Field(default='', max_length=500)


def preview(session, asset_id):
    asset = get_or_404(session, m.Asset, asset_id)
    text = chapterplans.source_text(asset)
    toc, latest, digest = chapterplans.plan(session, asset_id, text)
    return asset, text, toc, latest, digest


@router.get('/{asset_id}/chapter-plan')
def get_plan(asset_id: int, session: Session = Depends(get_session)):
    asset, text, toc, latest, digest = preview(session, asset_id)
    history = session.scalars(select(m.ChapterRevision).where(m.ChapterRevision.asset_id == asset_id).options(defer(m.ChapterRevision.chapters)).order_by(m.ChapterRevision.id.desc()).limit(100))
    return {'title': asset.title, 'length': len(text), 'text_hash': digest, 'base_revision': latest.id if latest else 0,
            'chapters': toc, 'detected': chapters.split_chapters(text),
            'stale': bool(latest and latest.text_hash != digest),
            'source': '原文件全文' if (asset.meta or {}).get('text_truncated') or (asset.original_name or '').lower().endswith('.epub') else '已保存正文',
            'history': [{'id': r.id, 'note': r.note, 'created_at': r.created_at.isoformat(), 'compatible': r.text_hash == digest} for r in history]}


@router.get('/{asset_id}/chapter-plan/excerpt')
def excerpt(asset_id: int, start: int = Query(0, ge=0), session: Session = Depends(get_session)):
    text = chapterplans.source_text(get_or_404(session, m.Asset, asset_id))
    if start > len(text):
        raise HTTPException(422, '位置超出正文')
    return {'start': start, 'text': text[start:start + 2000]}


def append(session, asset_id, req):
    _, text, _, latest, digest = preview(session, asset_id)
    if req.text_hash != digest or req.base_revision != (latest.id if latest else 0):
        raise HTTPException(409, '正文或目录版本已变化，请重新加载后比较')
    try:
        toc = chapters.validate_plan(text, [c.model_dump(exclude_none=True) for c in req.chapters])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    revision = m.ChapterRevision(asset_id=asset_id, parent_revision=req.base_revision, text_hash=digest, chapters=toc, note=req.note)
    session.add(revision)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, '目录被另一操作更新，请重新加载') from None
    return {'revision': revision.id, 'chapters': toc}


@router.put('/{asset_id}/chapter-plan')
def save(asset_id: int, req: PlanInput, session: Session = Depends(get_session)):
    return append(session, asset_id, req)


@router.get('/{asset_id}/chapter-plan/history/{revision_id}')
def history(asset_id: int, revision_id: int, session: Session = Depends(get_session)):
    row = get_or_404(session, m.ChapterRevision, revision_id)
    if row.asset_id != asset_id:
        raise HTTPException(404, '目录版本不存在')
    return {'id': row.id, 'chapters': row.chapters, 'text_hash': row.text_hash, 'note': row.note}
