"""Independent model archive; scan and metadata only. Renderer arrives separately."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session, defer

from .. import jobs, live2dscan
from ..models import Live2DProfile
from ..crud import get_or_404
from ..db import get_session, new_session

router = APIRouter(prefix='/api/live2d', tags=['Live2D Studio'])


class ProfileUpdate(BaseModel):
    title: str = Field(default='', min_length=1, max_length=300)
    creator: str = Field(default='', max_length=300)
    source_url: str = Field(default='', max_length=2000)
    license_notes: str = Field(default='', max_length=20000)
    model_version: str = Field(default='', max_length=100)
    favorite: bool = False
    stars: int = Field(default=0, ge=0, le=5)
    preference: int = Field(default=0, ge=0, le=100)
    labels: list[str] = Field(default_factory=list, max_length=100)
    notes: str = Field(default='', max_length=20000)


class ScanRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4000)
    creator: str = Field(default='', max_length=300)
    source_url: str = Field(default='', max_length=2000)
    license_notes: str = Field(default='', max_length=20000)


def record(profile, detail=True):
    fields = ('id', 'title', 'creator', 'source_url', 'license_notes', 'model_version',
              'favorite', 'stars', 'preference', 'labels', 'notes', 'source_path', 'main')
    result = {field: getattr(profile, field) for field in fields}
    if detail:
        result['scan'] = profile.scan
    return result


@router.get('/profiles')
def listing(q: str = '', limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), session: Session = Depends(get_session)):
    stmt = select(Live2DProfile)
    if q:
        stmt = stmt.where(Live2DProfile.title.contains(q, autoescape=True))
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = session.scalars(stmt.options(defer(Live2DProfile.scan)).order_by(Live2DProfile.favorite.desc(), Live2DProfile.id.desc()).limit(limit).offset(offset))
    return {'items': [record(p, False) for p in rows], 'total': total}


@router.get('/profiles/{profile_id}')
def detail(profile_id: int, session: Session = Depends(get_session)):
    return record(get_or_404(session, Live2DProfile, profile_id))


@router.patch('/profiles/{profile_id}')
def update(profile_id: int, req: ProfileUpdate, session: Session = Depends(get_session)):
    profile = get_or_404(session, Live2DProfile, profile_id)
    for key, value in req.model_dump(exclude_unset=True).items():
        if key == 'labels' and any(len(label) > 80 for label in value):
            raise HTTPException(422, '标签不能超过 80 字')
        setattr(profile, key, value)
    session.commit()
    return record(profile)


@router.post('/scan')
def scan(req: ScanRequest):
    path = Path(req.path).expanduser().resolve()
    if not path.exists():
        raise HTTPException(404, '路径不存在')

    def work(job):
        result = live2dscan.scan(path, job.check)
        job.total = len(result['models'])
        job.result = {'created': 0, 'updated': 0, 'profile_ids': [], 'errors': result['errors']}
        with new_session() as session:
            for model in result['models']:
                job.check()
                profile = session.scalar(select(Live2DProfile).where(Live2DProfile.identity == model['identity']))
                if profile is None:
                    profile = Live2DProfile(identity=model['identity'], title=model['title'], source_path=model['source_path'], main=model['main'], creator=req.creator, source_url=req.source_url, license_notes=req.license_notes)
                    session.add(profile)
                    job.result['created'] += 1
                else:
                    job.result['updated'] += 1
                profile.source_path, profile.main = model['source_path'], model['main']
                profile.scan = model
                session.commit()
                job.result['profile_ids'].append(profile.id)
                job.step(model['title'])
    return jobs.start('live2d-scan', f'扫描 Live2D：{path.name}', 0, work).to_dict()


@router.delete('/profiles/{profile_id}', status_code=204)
def remove(profile_id: int, session: Session = Depends(get_session)):
    session.delete(get_or_404(session, Live2DProfile, profile_id))
    session.commit()
    return Response(status_code=204)
