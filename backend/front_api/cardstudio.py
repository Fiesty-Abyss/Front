"""Character-card draft validation and identity; no inference engine or second library."""
import hashlib
import json
import threading
import re
from contextlib import contextmanager
from datetime import datetime, date

from fastapi import HTTPException

from . import models as m, schemas as s

MAX_IMPORT = 16 * 1024 * 1024
MAX_JSON = 1024 * 1024
_image_gate = threading.BoundedSemaphore(1)
TEXT_FIELDS = ('name', 'description', 'personality', 'scenario', 'first_mes', 'mes_example',
               'creator_notes', 'system_prompt', 'post_history_instructions', 'creator', 'character_version')


def identity(value):
    return value.replace(tzinfo=None).isoformat() if isinstance(value, datetime) else value.isoformat() if isinstance(value, date) else str(value)


@contextmanager
def image_operation():
    if not _image_gate.acquire(blocking=False):
        raise HTTPException(429, '已有角色卡导入/封面导出正在处理，请稍后重试')
    try:
        yield
    finally:
        _image_gate.release()


def scope(session, card):
    char = session.get(m.Character, card.character_id) if card.character_id else None
    book = session.get(m.Lorebook, card.lorebook_id) if card.lorebook_id else None
    return {'character_id': char.id if char else None, 'world_id': char.world_id if char else None,
            'work_id': char.work_id if char else None, 'lorebook_world_id': book.world_id if book else None}


def fingerprint(session, card):
    value = {c.key: getattr(card, c.key) for c in card.__table__.columns if c.key != 'updated_at'}
    value['_scope'] = scope(session, card)
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=identity).encode()).hexdigest()


def validate(session, data, obj_id=None):
    old = session.get(m.CharacterCard, obj_id) if obj_id else None
    combined = {f: getattr(old, f) for f in s.CardCreate.model_fields} if old else s.CardCreate(name='draft').model_dump()
    combined.update({key: value for key, value in data.items() if key in s.CardCreate.model_fields})
    for key in TEXT_FIELDS:
        value = combined.get(key)
        limit = 200 if key in ('name', 'creator') else 60 if key == 'character_version' else 250_000
        if not isinstance(value, str) or len(value) > limit or (key == 'name' and not value.strip()):
            raise HTTPException(422, f'角色卡字段 {key} 类型或长度不正确')
    for key in ('alternate_greetings', 'card_tags'):
        value = combined.get(key)
        if not isinstance(value, list) or len(value) > 100 or any(not isinstance(v, str) or len(v) > (200 if key == 'card_tags' else 20000) for v in value):
            raise HTTPException(422, f'角色卡字段 {key} 必须是有界文本列表')
    if not isinstance(combined.get('extensions'), dict):
        raise HTTPException(422, '角色卡扩展必须是 JSON 对象')
    design = combined['extensions'].get('front_design_v1')
    if isinstance(design, dict) and design.get('schema') == 1:
        for field in ('appearance', 'clothing', 'hair', 'eyes', 'notes'):
            if field in design and (not isinstance(design[field], str) or len(design[field]) > (30000 if field == 'notes' else 6000)):
                raise HTTPException(422, '外貌/备注字段类型或长度无效')
        if 'aliases' in design and (not isinstance(design['aliases'], list) or len(design['aliases']) > 30 or any(not isinstance(a, str) or len(a) > 200 for a in design['aliases'])):
            raise HTTPException(422, '别名必须是最多30项的文本列表')
        if 'favorite' in design and type(design['favorite']) is not bool:
            raise HTTPException(422, '收藏标志必须是布尔值')
        for key, maximum in (('stars', 5), ('preference', 100)):
            if key in design and (type(design[key]) is not int or not 0 <= design[key] <= maximum):
                raise HTTPException(422, '星级或喜爱度必须是有效范围内的整数')
    try:
        size = len(json.dumps(combined, ensure_ascii=False, allow_nan=False).encode())
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(422, '角色卡 JSON 结构或数值无效') from None
    if size > MAX_JSON:
        raise HTTPException(422, '角色卡字段总大小超过1MiB，请缩小文本或扩展')
    for key, model in (('character_id', m.Character), ('avatar_asset_id', m.Asset), ('lorebook_id', m.Lorebook)):
        if combined.get(key) is not None and not session.get(model, combined[key]):
            raise HTTPException(422, f'关联资料 {key} 不存在，未保存角色卡')
    char = session.get(m.Character, combined['character_id']) if combined.get('character_id') else None
    book = session.get(m.Lorebook, combined['lorebook_id']) if combined.get('lorebook_id') else None
    changed_scope = old is None or any(k in data and data[k] != getattr(old, k) for k in ('character_id', 'lorebook_id'))
    if changed_scope and char and book and book.world_id is not None and book.world_id != char.world_id:
        raise HTTPException(422, '角色与世界书属于不同世界观；请先明确整理关联，不自动跨世界混用')


def read_state(session, card):
    return {'card': s.CardRead.model_validate(card).model_dump(mode='json'),
            'expected': fingerprint(session, card), 'scope': scope(session, card)}


def from_character(session, char, oc=None):
    world = session.get(m.World, char.world_id) if char.world_id else None
    source = {'kind': 'front-character', 'character_id': char.id, 'created_at': char.created_at.isoformat(),
              'world_id': char.world_id, 'work_id': char.work_id}
    if oc:
        source['oc_id'] = oc.id
        source['oc_created_at'] = oc.created_at.isoformat()
    # Evidence remains in the original reviewed encyclopedia/extraction records; no novel copied.
    aliases = [a.strip() for a in re.split(r'[,，、]', char.alias or '') if a.strip()]
    extensions = {'front_source_v1': source}
    if aliases:
        extensions['front_design_v1'] = {'schema': 1, 'aliases': aliases}
    if oc:
        extensions['front_oc_designs_v1'] = {'fields': oc.fields, 'designs': oc.designs}
    return {'name': char.name, 'description': '\n\n'.join(v for v in (char.summary, char.profile) if v),
            'scenario': (world.summary or '') if world else '', 'card_tags': [t.name for t in char.tags],
            'character_id': char.id, 'avatar_asset_id': char.avatar_asset_id,
            'creator_notes': '由 Front 已有角色资料创建的独立创作草稿；原百科与小说保持不变。',
            'extensions': extensions}
