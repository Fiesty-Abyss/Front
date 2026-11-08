import hashlib
import json
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from .. import jobs, metadata as md, models as m, versions
from ..crud import get_or_404
from ..db import get_session
from ..galgame import meta

router = APIRouter(prefix='/api/metadata', tags=['联网资料匹配'])
Identity = Annotated[int, Path(ge=1, le=2**63-1)]
Target = Literal['work', 'galgame']
FIELDS = {'work': ('title', 'description', 'year', 'publisher', 'url'),
          'galgame': ('title', 'title_cn', 'original', 'description', 'developer', 'release_date', 'platforms', 'source_tags', 'aliases', 'cover_url')}
EXTRAS = ('authors', 'aliases', 'tags', 'covers')


@event.listens_for(m.Work, 'before_update')
@event.listens_for(m.Galgame, 'before_update')
def track_manual(_mapper, _connection, row):
    if getattr(row, '_metadata_write', False):
        return
    catalog = row.metadata_catalog
    if not isinstance(catalog, dict) or catalog.get('schema') != 1 or not isinstance(catalog.get('fields'), dict):
        return
    revised = json.loads(json.dumps(catalog))
    for field, record in revised['fields'].items():
        if field in inspect(row).attrs and inspect(row).attrs[field].history.has_changes():
            record['manual'] = getattr(row, field) != record.get('applied_value')
    if revised != catalog:
        row.metadata_catalog = revised


class Search(BaseModel):
    model_config = ConfigDict(extra='forbid')
    online: Literal[True]
    kind: Literal['book', 'game', 'model']
    title: str = Field(min_length=1, max_length=95)
    author: str | None = Field(default=None, max_length=95)
    year: StrictInt | None = Field(default=None, ge=1, le=9999)
    providers: list[str] = Field(min_length=1, max_length=4)


class Detail(BaseModel):
    model_config = ConfigDict(extra='forbid')
    online: Literal[True]
    kind: Literal['book', 'game', 'model']
    provider: str
    sid: str = Field(min_length=1, max_length=80)


class Apply(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected: str = Field(pattern=r'^[a-f0-9]{64}$')
    receipt: str = Field(pattern=r'^[a-f0-9]{32}$')
    fields: list[str] = Field(min_length=1, max_length=20)
    replace: list[str] = Field(default_factory=list, max_length=20)
    allow_refresh: list[str] = Field(default_factory=list, max_length=20)


@router.get('/providers')
def providers():
    return {'items': md.capabilities(), 'unavailable': [
        {'id': 'google_books', 'reason': '尚未配置专用图书 API 身份，未接入'},
        {'id': 'nextmoe', 'reason': '公开接口与使用许可仍待核实，未接入'}]}


def validate_provider(name, kind):
    if not md.enabled():
        raise HTTPException(403, '联网资料匹配已关闭；本地浏览仍可使用')
    if name not in md.PROVIDERS or kind not in md.PROVIDERS[name].kinds:
        raise HTTPException(422, '来源不支持这种资料；聊天 Provider 不作为资料或图像接口')


@router.post('/search', status_code=202)
def search(body: Search, session: Session = Depends(get_session)):
    if not body.title.strip() or len(set(body.providers)) != len(body.providers):
        raise HTTPException(422, '请输入检索词，来源不可重复')
    for name in body.providers:
        validate_provider(name, body.kind)
    if body.kind == 'model' and not re.fullmatch(r'[a-fA-F0-9]{64}', body.title):
        raise HTTPException(422, '模型仅支持 SHA256 查询，不发送本地路径')
    query = body.model_dump(exclude={'online'})
    cfg = meta.load_settings(session)
    return jobs.start('metadata-search', '用户主动资料检索', len(body.providers), lambda job: md.run(job, 'search', query, cfg)).to_dict()


@router.post('/detail', status_code=202)
def detail(body: Detail, session: Session = Depends(get_session)):
    validate_provider(body.provider, body.kind)
    pattern = r'OL\d+W' if body.provider == 'openlibrary' else r'[a-fA-F0-9]{64}' if body.provider == 'civitai' else r'v?\d{1,18}'
    if not re.fullmatch(pattern, body.sid):
        raise HTTPException(422, '无效的来源条目 ID')
    cfg = meta.load_settings(session)
    query = {'kind': body.kind, 'providers': [body.provider], 'sid': body.sid}
    return jobs.start('metadata-detail', '用户主动读取资料详情', 1, lambda job: md.run(job, 'detail', query, cfg)).to_dict()


def target(session, kind, entity_id):
    row = get_or_404(session, m.Work if kind == 'work' else m.Galgame, entity_id)
    catalog = row.metadata_catalog or {'schema': 1, 'fields': {}}
    if not isinstance(catalog, dict) or catalog.get('schema') != 1 or not isinstance(catalog.get('fields'), dict) or any(not isinstance(v, dict) for v in catalog.get('fields', {}).values()):
        raise HTTPException(409, '资料来源记录由较新版本创建，拒绝覆盖')
    values = {f: getattr(row, f) for f in FIELDS[kind]}
    values.update({f: catalog['fields'].get(f, {}).get('applied_value') for f in EXTRAS if f not in values})
    state = {'id': row.id, 'identity': row.created_at.isoformat(), 'kind': getattr(row, 'kind', 'game'), 'values': values, 'catalog': catalog}
    fingerprint = hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return row, state | {'expected': fingerprint}


@router.get('/targets/{kind}/{entity_id}')
def get_target(kind: Target, entity_id: Identity, session: Session = Depends(get_session)):
    return target(session, kind, entity_id)[1]


@router.post('/targets/{kind}/{entity_id}/apply')
def apply(kind: Target, entity_id: Identity, body: Apply, session: Session = Depends(get_session)):
    receipt = md.receipt(body.receipt)
    item = receipt['item']
    if item['kind'] == 'model' or (kind == 'galgame' and item['kind'] != 'game'):
        raise HTTPException(422, '来源资料类型与目标不兼容')
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    row, state = target(session, kind, entity_id)
    if state['expected'] != body.expected:
        raise HTTPException(409, '本地资料已变化，请重新载入并核对字段')
    if kind == 'work' and state['kind'] not in ('other', {'book': 'novel', 'game': 'game'}[item['kind']], 'galgame' if item['kind'] == 'game' else 'manga'):
        raise HTTPException(409, '目标作品类型不同；不自动把改编版或原创企划合并')
    proposed = {**item, 'release_date': item.get('date'), 'source_tags': item.get('tags'), 'cover_url': next(iter(item.get('covers') or []), None)}
    if item.get('date') and str(item['date'])[:4].isdigit():
        proposed['year'] = int(item['date'][:4])
    allowed = set(FIELDS[kind]) | set(EXTRAS)
    selected = set(body.fields)
    if not selected <= allowed or not set(body.replace) <= selected or not set(body.allow_refresh) <= selected:
        raise HTTPException(422, '无效的资料字段选择')
    catalog = json.loads(json.dumps(state['catalog']))
    changes = {}
    for field in selected:
        value = proposed.get(field)
        if value in (None, '', []):
            continue
        current = state['values'].get(field)
        old = catalog['fields'].get(field, {})
        can_refresh = bool(old.get('allow_refresh') and old.get('provider') == item['provider'] and old.get('source_id') == item['sid'] and current == old.get('applied_value'))
        manual = current != old.get('applied_value') if old else current not in (None, '', [])
        if current != value and field not in body.replace and (manual or (current not in (None, '', []) and not can_refresh)):
            raise HTTPException(409, f'字段 {field} 有人工内容或未允许刷新，请明确确认替换')
        if current == value and old and old.get('provider') == item['provider'] and old.get('source_id') == item['sid'] and old.get('allow_refresh') == (field in body.allow_refresh):
            continue
        catalog['fields'][field] = {'provider': item['provider'], 'source_id': item['sid'], 'source_url': item['url'], 'fetched_at': receipt['fetched_at'],
                                     'raw_value': value, 'applied_value': value, 'manual_replacement_confirmed': field in body.replace,
                                     'allow_refresh': field in body.allow_refresh, 'manual': False}
        if field in FIELDS[kind]:
            changes[field] = value
    if catalog == state['catalog']:
        return {'changed': False, **state}
    versions.enable(session, row, '联网资料应用前快照')
    row._metadata_write = True
    if kind == 'galgame':
        row._meta_write = True
        # Legacy game refresh must not silently overwrite fields reviewed in this center.
        row.overrides = sorted(set(row.overrides or []) | set(changes))
    for field, value in changes.items():
        setattr(row, field, value)
    row.metadata_catalog = catalog
    session.flush()
    session.commit()
    return {'changed': True, **target(session, kind, entity_id)[1]}
