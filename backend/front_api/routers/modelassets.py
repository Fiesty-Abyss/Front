"""Bounded read-only scan reports and engine-independent personal model records."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import jobs, modelscan, models as m, sdgen
from ..config import get_settings
from ..crud import get_or_404
from ..db import get_session, new_session
from .sdtools import ScanRequest, _scan_root, _existing, _hash_model

router = APIRouter(tags=['模型资产'])


@router.post('/api/model-assets/{model_id}/hash')
def hash_model(model_id: int, session: Session = Depends(get_session)):
    get_or_404(session, m.SDModel, model_id)
    def work(job):
        with new_session() as db:
            row=get_or_404(db,m.SDModel,model_id)
            _hash_model(db,row,job.check)
            db.commit()
            job.result={'model_id':model_id}
            job.step()
    return jobs.start('model-hash','计算模型哈希',1,work).to_dict()


@router.post('/api/model-assets/scan')
def scan(body: ScanRequest):
    root = _scan_root(body.path)
    report_id = uuid.uuid4().hex
    def work(job):
        paths = modelscan.iter_model_files(root, body.recursive, job.check)
        job.total = len(paths)
        items, kinds = [], {}
        with new_session() as session:
            for path in paths:
                job.check()
                try:
                    item = modelscan.describe(path, root, with_hash=body.compute_hash, check=job.check)
                    existing = _existing(session, item)
                    item['existing_id'] = existing.id if existing else None
                    item.pop('civitai_info', None)
                    item.pop('metadata', None)
                    kinds[item['kind']] = kinds.get(item['kind'], 0) + 1
                    items.append(item)
                except OSError:
                    job.errors.append(f'无法读取模型：{path.name}')
                job.step(path.name)
        result = {'id': report_id, 'root': str(root), 'total': len(items), 'kinds': kinds,
                  'new': sum(not i['existing_id'] for i in items), 'total_size': sum(i['size'] for i in items),
                  'items': items, 'runtime_verified': False}
        folder = get_settings().data_dir / 'project-previews'
        folder.mkdir(parents=True, exist_ok=True)
        temp = folder / f'model-{report_id}.tmp'
        temp.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        temp.replace(folder / f'model-{report_id}.json')
        job.result = {'report_id': report_id, 'total': len(items), 'kinds': kinds}
    return jobs.start('model-preview', '只读模型扫描', 0, work).to_dict()


@router.get('/api/model-assets/reports/{report_id}')
def report(report_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    if len(report_id) != 32 or any(c not in '0123456789abcdef' for c in report_id):
        raise HTTPException(404, '扫描报告不存在')
    path = get_settings().data_dir / 'project-previews' / f'model-{report_id}.json'
    if not path.is_file():
        raise HTTPException(404, '扫描报告不存在')
    data = json.loads(path.read_text(encoding='utf-8'))
    data['items'] = data['items'][offset:offset+limit]
    return data


class Profile(BaseModel):
    favorite: bool = False
    stars: int = Field(0, ge=0, le=5)
    preference: int = Field(0, ge=0, le=100)
    style: str = Field('', max_length=4000)
    scenes: str = Field('', max_length=4000)
    usage_notes: str = Field('', max_length=12000)
    # Registry names only; no endpoint, credentials, config writing or discovery requests.
    engine_mappings: dict[Literal['webui', 'forge', 'comfyui'], str] = Field(default_factory=dict, max_length=3)


def read_profile(session, model_id):
    get_or_404(session, m.SDModel, model_id)
    row = session.get(m.SDModelProfile, model_id)
    return {**(Profile.model_validate(row, from_attributes=True).model_dump() if row else Profile().model_dump()),
            'observation': row.observation if row else {}}


@router.get('/api/model-assets/{model_id}/profile')
def profile(model_id: int, session: Session = Depends(get_session)):
    return read_profile(session, model_id)


@router.put('/api/model-assets/{model_id}/profile')
def save_profile(model_id: int, body: Profile, session: Session = Depends(get_session)):
    get_or_404(session, m.SDModel, model_id)
    if any(not name.strip() or len(name) > 300 or '\x00' in name for name in body.engine_mappings.values()):
        raise HTTPException(422, '目标引擎模型名称应为1–300字')
    row = session.get(m.SDModelProfile, model_id) or m.SDModelProfile(model_id=model_id)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    session.add(row)
    session.commit()
    return read_profile(session, model_id)


class Compatibility(BaseModel):
    engine: Literal['webui', 'forge', 'comfyui']
    model_ids: list[int] = Field(min_length=1, max_length=30)


def family(value):
    value = (value or '').lower()
    if value in ('sdxl', 'pony', 'illustrious'):
        return 'sdxl'
    return value if value in ('sd1.5', 'sd2', 'flux', 'sd3') else None


@router.post('/api/model-assets/compatibility')
def compatibility(body: Compatibility, session: Session = Depends(get_session)):
    rows = [get_or_404(session, m.SDModel, i) for i in set(body.model_ids)]
    families = {family(r.base_model) for r in rows if r.kind in ('checkpoint', 'lora', 'lycoris', 'vae')} - {None}
    mismatch = len(families) > 1
    result = []
    for row in rows:
        p = session.get(m.SDModelProfile, row.id)
        mapped = (p.engine_mappings or {}).get(body.engine) if p else None
        result.append({'model_id': row.id, 'architecture': row.base_model, 'mapped_name': mapped,
                       'catalog_verified': False, 'runtime_verified': False,
                       'status': 'incompatible' if mismatch else 'unverified',
                       'reason': '已登记底模架构不一致，请核对' if mismatch else '仅为登记资料；需要目标引擎目录和工作流实际验证'})
    return {'items': result, 'status': 'incompatible' if mismatch else 'unverified',
            'configuration_changed': False}


class Catalog(BaseModel):
    engine: Literal['webui', 'forge', 'comfyui']
    confirm_connect: Literal[True]
    model_ids: list[int] = Field(default_factory=list, max_length=100)


@router.post('/api/model-assets/catalog-check')
def catalog_check(body: Catalog, session: Session = Depends(get_session)):
    """Explicit read-only connection to an already configured running service; never starts it."""
    rows = [get_or_404(session, m.SDModel, mid) for mid in body.model_ids]
    backend = 'comfyui' if body.engine == 'comfyui' else 'webui'
    try:
        url = sdgen.backend_url(backend)
        options = sdgen.comfy_options(url) if backend == 'comfyui' else sdgen.webui_options(url)
    except sdgen.BackendError as exc:
        raise HTTPException(503, '生成服务未配置或无法连接；未修改或启动外部软件') from exc
    out=[]
    for row in rows:
        p=session.get(m.SDModelProfile,row.id)
        name=(p.engine_mappings or {}).get(body.engine) if p else None
        name=name or row.file_name
        names=options.get('loras' if row.kind in ('lora','lycoris') else 'models',[])
        # WebUI catalogue model names may include its display hash.
        found=bool(name and any(name==n or name==str(n).split(' [')[0] for n in names))
        out.append({'model_id':row.id,'mapped_name':name,'catalog_verified':found,'runtime_verified':False})
    return {'items':out,'configuration_changed':False,'generation_performed':False}
