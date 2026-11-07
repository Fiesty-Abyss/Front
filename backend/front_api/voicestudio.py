"""Voice metadata validation. No engine imports, network requests or weight reads."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from . import models as m, versions
from .crud import get_or_404


class Draft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default='', max_length=20000)
    expected_uid: str | None = None
    expected_version: int | None = None

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError('名称不能为空')
        return value.strip()


class ProviderDraft(Draft):
    engine: str = Field(default='unconfigured', pattern=r'^(unconfigured|gpt_sovits|custom)$')
    endpoint: str = Field(default='', max_length=2000)
    credential_id: int | None = Field(default=None, gt=0)

    @field_validator('endpoint')
    @classmethod
    def clean_endpoint(cls, value):
        if not value:
            return value
        try:
            url = urlsplit(value)
            if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError()
            _ = url.port
        except ValueError:
            raise ValueError('服务地址须为不含凭据、查询参数及片段的 HTTP(S) 地址') from None
        return value.rstrip('/')


class ModelDraft(Draft):
    provider_id: int | None = Field(default=None, gt=0)
    file_path: str = Field(default='', max_length=2000)
    model_version: str = Field(default='', max_length=200)
    source: str = Field(default='', max_length=2000)
    license: str = Field(default='', max_length=20000)


class ProfileDraft(Draft):
    model_id: int | None = Field(default=None, gt=0)
    character_id: int | None = Field(default=None, gt=0)
    oc_id: int | None = Field(default=None, gt=0)
    sample_ref: dict = Field(default_factory=dict)
    voice_key: str = Field(default='', max_length=200)
    language: str = Field(default='', max_length=40)
    source: str = Field(default='', max_length=2000)
    license: str = Field(default='', max_length=20000)
    favorite: bool = False
    stars: int = Field(default=0, ge=0, le=5)
    preference: int = Field(default=0, ge=0, le=100)
    tag_ids: list[int] = Field(default_factory=list, max_length=100)


def identity(obj):
    return obj.created_at.replace(tzinfo=None).isoformat()


def binding(session, character_id, oc_id):
    """Snapshot canonical scope; never merge characters by name."""
    if character_id and oc_id:
        raise HTTPException(422, '请选择角色或 OC 其中一种绑定')
    result = {}
    if oc_id:
        oc = get_or_404(session, m.OCProfile, oc_id)
        result['oc'] = [oc.id, identity(oc)]
        character_id = oc.character_id
    if character_id:
        char = get_or_404(session, m.Character, character_id)
        result['character'] = [char.id, identity(char)]
        for kind, model, key in [('world', m.World, char.world_id), ('work', m.Work, char.work_id)]:
            obj = session.get(model, key) if key else None
            result[kind] = [obj.id, identity(obj)] if obj else None
    return result


def sample(session, ref):
    if not ref:
        return {}
    if set(ref) != {'id', 'identity', 'sha256'} or type(ref.get('id')) is not int:
        raise HTTPException(422, '试听素材须携带 id、identity 与 sha256')
    asset = get_or_404(session, m.Asset, ref['id'])
    if asset.kind != 'audio':
        raise HTTPException(422, '试听样本必须是素材库音频')
    if identity(asset) != ref['identity'] or asset.sha256 != ref['sha256']:
        raise HTTPException(409, '试听素材已变化，请重新选择')
    return ref


def validate(session, obj, data):
    if isinstance(obj, m.VoiceProvider) and data.get('credential_id'):
        get_or_404(session, m.AIProviderConfig, data['credential_id'])
    if isinstance(obj, m.VoiceModel) and data.get('provider_id'):
        get_or_404(session, m.VoiceProvider, data['provider_id'])
    if isinstance(obj, m.VoiceProfile):
        if data.get('model_id'):
            get_or_404(session, m.VoiceModel, data['model_id'])
        scope = binding(session, data.get('character_id'), data.get('oc_id'))
        # Re-saving the same binding cannot silently accept a world move.
        if obj.id and obj.character_id == data.get('character_id') and obj.oc_id == data.get('oc_id') and obj.binding != scope:
            raise HTTPException(409, '角色归属已变化；请先解除绑定再确认新的关联')
        data['binding'] = scope
        data['sample_ref'] = sample(session, data.get('sample_ref') or {})
        if data['sample_ref'] and scope.get('world'):
            asset = session.get(m.Asset, data['sample_ref']['id'])
            if asset.world_id and asset.world_id != scope['world'][0]:
                raise HTTPException(422, '试听素材属于不同世界观，请明确选择同范围或无归属的音频')


def validate_restore(session, obj, data):
    if data.get('uid') != obj.uid:
        raise HTTPException(409, '历史记录身份不匹配')
    if isinstance(obj, m.VoiceProfile):
        current = binding(session, obj.character_id, obj.oc_id)
        target = binding(session, data.get('character_id'), data.get('oc_id'))
        if target != data.get('binding') or current != data.get('_voice_scope'):
            raise HTTPException(409, '历史声线关联的角色或世界观已变化，请手动审核')
        sample(session, data.get('sample_ref') or {})


def diagnostics(session, obj):
    issues = []
    try:
        if obj.binding != binding(session, obj.character_id, obj.oc_id):
            issues.append('角色或世界观关联已变化，请审核')
        sample(session, obj.sample_ref)
    except HTTPException as exc:
        issues.append(str(exc.detail))
    return issues


def version_id(session, obj):
    h = versions.head(session.connection(), versions.KINDS[type(obj)], obj.id)
    last = versions.latest(session.connection(), h['generation']) if h and h['enabled'] and h['present'] else None
    return last['id'] if last else None


def guard(session, obj, uid, expected):
    if uid != obj.uid or expected != version_id(session, obj) or expected is None:
        raise HTTPException(409, '档案已变化，请刷新后重试')


def serialize(session, obj, detail=True):
    omitted = set() if detail else {'notes', 'license', 'binding', 'sample_ref'}
    value = {c.key: getattr(obj, c.key) for c in obj.__table__.columns if c.key not in omitted}
    value['version'] = version_id(session, obj)
    if isinstance(obj, m.VoiceProfile):
        value['tag_ids'] = [t.id for t in obj.tags]
        if detail:
            value['issues'] = diagnostics(session, obj)
    if isinstance(obj, m.VoiceProvider):
        value['capabilities'] = {'verified': False, 'synthesize': False, 'training': False}
        value['status'] = 'not_connected'
    value['fingerprint'] = hashlib.sha256(json.dumps(
        {k: v for k, v in value.items() if k not in ('created_at', 'updated_at', 'version', 'issues')},
        sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return value


def inspect_file(path):
    """Explicit local stat only; no recursive scan, hash or weights deserialization."""
    if not path:
        return {'status': 'unregistered', 'runtime_verified': False}
    if path.startswith(('\\\\', '//')) or '://' in path or not Path(path).is_absolute():
        return {'status': 'unsupported_path', 'runtime_verified': False}
    try:
        p = Path(path)
        if not p.is_file():
            return {'status': 'missing', 'runtime_verified': False}
        st = p.stat()
        return {'status': 'file_present', 'size': st.st_size, 'mtime_ns': st.st_mtime_ns,
                'runtime_verified': False, 'compatibility': 'unknown'}
    except OSError:
        return {'status': 'unreadable', 'runtime_verified': False}
