"""Voice Studio foundation. Metadata requests never contact an inference service."""
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, func
from sqlalchemy.orm import Session, defer
from .. import models as m, versions as v, voicestudio as vs
from ..crud import get_or_404, resolve_tags
from ..db import get_session

router = APIRouter(prefix='/api/voice', tags=['AI Voice Studio'])


def register(resource, model, schema):
    prefix = '/' + resource

    @router.get(prefix)
    def listing(q: str = Query('', max_length=200), favorite: bool | None = None,
                tag: list[int] = Query(default=[]), limit: int = Query(50, ge=1, le=100),
                offset: int = Query(0, ge=0), session: Session = Depends(get_session)):
        query = select(model)
        if q:
            query = query.where(model.title.contains(q, autoescape=True))
        if model is m.VoiceProfile:
            if favorite is not None:
                query = query.where(model.favorite == favorite)
            for tid in tag:
                query = query.where(model.tags.any(m.Tag.id == tid))
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        # Large notes/license never enter list queries or responses.
        query = query.options(defer(model.notes))
        if hasattr(model, 'license'):
            query = query.options(defer(model.license))
        rows = session.scalars(query.order_by(model.id.desc()).offset(offset).limit(limit)).all()
        return {'total': total, 'items': [vs.serialize(session, obj, False) for obj in rows]}

    @router.get(prefix + '/{obj_id}')
    def detail(obj_id: int, session: Session = Depends(get_session)):
        return vs.serialize(session, get_or_404(session, model, obj_id))

    @router.post(prefix, status_code=201)
    def create(body: schema, session: Session = Depends(get_session)):
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        data = body.model_dump(exclude={'expected_uid', 'expected_version'})
        obj = model()
        vs.validate(session, obj, data)
        tag_ids = data.pop('tag_ids', [])
        for key, value in data.items():
            setattr(obj, key, value)
        if model is m.VoiceProfile:
            obj.tags = resolve_tags(session, tag_ids)
        session.add(obj)
        session.flush()
        v.enable(session, obj, '新建声线资料')
        session.commit()
        return vs.serialize(session, obj)

    @router.put(prefix + '/{obj_id}')
    def update(obj_id: int, body: schema, session: Session = Depends(get_session)):
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        obj = get_or_404(session, model, obj_id)
        vs.guard(session, obj, body.expected_uid, body.expected_version)
        data = body.model_dump(exclude={'expected_uid', 'expected_version'})
        vs.validate(session, obj, data)
        tag_ids = data.pop('tag_ids', [])
        for key, value in data.items():
            setattr(obj, key, value)
        if model is m.VoiceProfile:
            obj.tags = resolve_tags(session, tag_ids)
        session.flush()
        v.record(session, obj)
        session.commit()
        return vs.serialize(session, obj)

    # There is deliberately no file deletion or service-start endpoint.


register('providers', m.VoiceProvider, vs.ProviderDraft)
register('models', m.VoiceModel, vs.ModelDraft)
register('profiles', m.VoiceProfile, vs.ProfileDraft)


@router.post('/models/{obj_id}/diagnose')
def diagnose(obj_id: int, session: Session = Depends(get_session)):
    obj = get_or_404(session, m.VoiceModel, obj_id)
    return vs.inspect_file(obj.file_path)
