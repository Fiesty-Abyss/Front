"""角色卡：在线编辑、导入（JSON / PNG）、导出（V2 JSON / 嵌入 PNG）。"""

from __future__ import annotations

import json
import re
import io
import hashlib
import threading
from typing import Literal
from typing import Any, Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query, Path as APIPath
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field
from PIL import Image, UnidentifiedImageError

from .. import models as m
from .. import schemas as s
from .. import cardstudio as studio, versions
from .. import cardassist, jobs
from ..config import get_settings
from ..crud import get_or_404, make_crud_router, apply_payload
from ..db import get_session
from ..ai import lore as lore_mod
from ..pngmeta import card_to_v2, read_card_png, v2_to_fields, write_card_png


def _v2(session: Session, card: m.CharacterCard) -> dict[str, Any]:
    """导出 V2：附带角色卡关联的世界书（character_book）。"""
    data = card_to_v2(card)
    if card.lorebook_id:
        book = session.get(m.Lorebook, card.lorebook_id)
        if book is not None:
            data["data"]["character_book"] = lore_mod.book_to_v2(book)
    return data

router = make_crud_router(
    prefix="/api/cards", model=m.CharacterCard, create_schema=s.CardCreate,
    update_schema=s.CardUpdate, read_schema=s.CardRead, tag_name="角色卡",
    validate=studio.validate, validate_with_id=True,
)
io_router = APIRouter(prefix="/api/cards", tags=["角色卡"])
CardId = Annotated[int, APIPath(ge=1, le=2**63-1)]
DraftId = Annotated[str, APIPath(pattern=r'^[a-f0-9]{32}$')]


class ReviewedSave(BaseModel):
    model_config = ConfigDict(extra='forbid')
    card: s.CardCreate
    card_id: int | None = Field(default=None, ge=1, le=2**63-1)
    expected: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    draft_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


class Assist(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider_id: int = Field(ge=1, le=2**63-1)
    brief: str = Field(min_length=1, max_length=12000)
    style: str = Field(default='', max_length=200)


class Generate(Assist):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    request_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirm_send: Literal[True]
    confirm_remote: bool = False


def draft_output(row):
    return {'id': row.id, 'status': row.status, 'fields': row.fields, 'provider': row.provider,
            'source': row.source, 'error': row.error, 'job_id': row.job_id, 'adopted_id': row.adopted_id,
            'created_at': row.created_at}


@io_router.get('/summaries')
def summaries(q: str = Query('', max_length=95), limit: int = Query(20, ge=1, le=100),
              offset: int = Query(0, ge=0), session: Session = Depends(get_session)):
    from ..search import matching_ids
    cols = (m.CharacterCard.id, m.CharacterCard.name, m.CharacterCard.avatar_asset_id, m.CharacterCard.creator,
            m.CharacterCard.character_version, m.CharacterCard.card_tags, m.CharacterCard.character_id)
    stmt = select(*cols)
    if q.strip():
        stmt = stmt.where(m.CharacterCard.id.in_(matching_ids(session, 'card', q)))
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = session.execute(stmt.order_by(m.CharacterCard.id.desc()).offset(offset).limit(limit)).mappings()
    return {'items': [dict(r) for r in rows], 'total': total}


@io_router.get('/choices')
def choices(kind: Literal['character', 'oc', 'image', 'lorebook'], q: str = Query('', max_length=95),
            world_id: int | None = Query(None, ge=1, le=2**63-1), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
            session: Session = Depends(get_session)):
    model, label = {'character': (m.Character, m.Character.name), 'oc': (m.OCProfile, m.OCProfile.title),
                    'image': (m.Asset, m.Asset.title), 'lorebook': (m.Lorebook, m.Lorebook.name)}[kind]
    cols = [model.id, label.label('name')]
    if kind == 'character':
        cols += [model.world_id, model.work_id]
    if kind == 'oc':
        cols += [model.character_id]
    if kind == 'lorebook':
        cols += [model.world_id]
    stmt = select(*cols)
    if q:
        stmt = stmt.where(label.contains(q, autoescape=True))
    if kind == 'image':
        stmt = stmt.where(m.Asset.width.is_not(None))
    if kind == 'lorebook' and world_id is not None:
        stmt = stmt.where((model.world_id == world_id) | model.world_id.is_(None))
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    return {'items': [dict(r) for r in session.execute(stmt.order_by(label, model.id).offset(offset).limit(limit)).mappings()], 'total': total}


@io_router.get('/{card_id}/draft-state')
def draft_state(card_id: CardId, session: Session = Depends(get_session)):
    return studio.read_state(session, get_or_404(session, m.CharacterCard, card_id))


@io_router.post('/save-reviewed')
def save_reviewed(body: ReviewedSave, session: Session = Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    data = body.card.model_dump()
    try:
        proposal = cardassist.digest(data)
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(422, '角色卡JSON数值或结构无效') from None
    draft = get_or_404(session, m.CharacterCardDraft, body.draft_id) if body.draft_id else None
    if draft:
        if draft.adopted_id is not None:
            existing = session.get(m.CharacterCard, draft.adopted_id)
            if draft.adopted_hash == proposal and existing and studio.identity(existing.created_at) == draft.adopted_identity and body.card_id in (None, existing.id):
                return studio.read_state(session, existing) | {'repeated': True}
            raise HTTPException(409, '此AI草稿已采用或目标已失效；请作为独立人工编辑保存，不重复创建')
        if draft.status != 'ready':
            raise HTTPException(409, 'AI草稿尚未完成，不能采用')
    row = get_or_404(session, m.CharacterCard, body.card_id) if body.card_id else m.CharacterCard()
    if body.card_id and (not body.expected or body.expected != studio.fingerprint(session, row)):
        raise HTTPException(409, '角色卡已被其他窗口修改，请先重新载入并核对，不覆盖新版本')
    studio.validate(session, data, body.card_id)
    if draft:
        data['extensions'] = {**data['extensions'], 'front_assist_v1': {'draft_id': draft.id, 'provider': draft.provider,
                                'input_sha256': draft.source.get('input_sha256'), 'user_reviewed': True,
                                'edited_fields': sorted(k for k, value in draft.fields.items() if data.get(k) != value)}}
        studio.validate(session, data, body.card_id)
    if body.card_id:
        versions.enable(session, row, '角色卡编辑前快照')
    apply_payload(session, row, data)
    session.add(row)
    session.flush()
    if not body.card_id:
        versions.enable(session, row, '创建角色卡草稿')
    if draft:
        draft.adopted_id, draft.adopted_identity, draft.adopted_hash = row.id, studio.identity(row.created_at), proposal
    session.commit()
    return studio.read_state(session, row)


@io_router.post('/assist/prepare')
def prepare(body: Assist, session: Session = Depends(get_session)):
    return cardassist.prepare(session, body.provider_id, body.brief, body.style)[0]


@io_router.post('/assist/generate', status_code=202)
def generate(body: Generate, session: Session = Depends(get_session)):
    gate = threading.Event()
    with cardassist._enqueue_lock:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        prepared, provider = cardassist.prepare(session, body.provider_id, body.brief, body.style)
        if prepared['request_hash'] != body.request_hash:
            raise HTTPException(409, '发送内容、服务或模型配置已变化，请重新预览和确认')
        if prepared['remote'] and not body.confirm_remote:
            raise HTTPException(422, '所选服务不在字面回环地址；请明确确认将预览文本发给该服务')
        old = session.get(m.CharacterCardDraft, body.request_id)
        if old:
            if old.request_hash != body.request_hash:
                raise HTTPException(409, '请求身份已被其他内容使用，请重新预览')
            if cardassist.reconcile(old):
                session.commit()
            return draft_output(old)
        row = m.CharacterCardDraft(id=body.request_id, request_hash=body.request_hash, provider=prepared['provider'],
             source={'input_sha256': prepared['input_sha256'], 'input_characters': prepared['input_characters'], 'kind': 'explicit-user-brief'})
        session.add(row)
        session.flush()
        try:
            job = jobs.start('card-assist', '已确认文本生成角色卡草稿', 1,
                             lambda job: cardassist.run(job, gate, row.id, prepared, provider))
            row.job_id = job.id
            session.commit()
        finally:
            gate.set()
    return draft_output(row)


@io_router.get('/assist/drafts')
def list_drafts(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), session: Session = Depends(get_session)):
    rows = session.scalars(select(m.CharacterCardDraft).order_by(m.CharacterCardDraft.created_at.desc(), m.CharacterCardDraft.id).offset(offset).limit(limit)).all()
    return {'items': [{'id': row.id, 'status': row.status, 'created_at': row.created_at, 'adopted_id': row.adopted_id} for row in rows],
            'total': session.scalar(select(func.count()).select_from(m.CharacterCardDraft))}


@io_router.get('/assist/drafts/{draft_id}')
def get_draft(draft_id: DraftId, session: Session = Depends(get_session)):
    row = get_or_404(session, m.CharacterCardDraft, draft_id)
    if cardassist.reconcile(row):
        session.commit()
    return draft_output(row)


@io_router.post('/assist/drafts/{draft_id}/cancel')
def cancel_draft(draft_id: DraftId, session: Session = Depends(get_session)):
    row = get_or_404(session, m.CharacterCardDraft, draft_id)
    job = jobs.get(row.job_id) if row.job_id else None
    if job and row.status in ('queued', 'running'):
        job.cancel_requested = True
    return draft_output(row)


@io_router.post('/from-oc/{profile_id}', response_model=s.CardRead, status_code=201)
def from_oc(profile_id: CardId, session: Session = Depends(get_session)):
    from ..ocstudio import character
    oc = get_or_404(session, m.OCProfile, profile_id)
    char = character(session, oc)
    if not char:
        raise HTTPException(409, 'OC关联角色已失效；请先在OC Studio审核关联')
    data = studio.from_character(session, char, oc)
    studio.validate(session, data)
    row = m.CharacterCard(**data)
    session.add(row)
    session.flush()
    versions.enable(session, row, '由OC建立角色卡草稿')
    session.commit()
    return row


def _filename(name: str, ext: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "card"
    return f"{safe}.{ext}"


def _disposition(name: str) -> str:
    return f"attachment; filename=card; filename*=UTF-8''{quote(name)}"


@io_router.post("/import", response_model=s.CardRead, status_code=201)
async def import_card(file: UploadFile = File(...), session: Session = Depends(get_session)) -> Any:
    with studio.image_operation():
        return await _import_card(file, session)


async def _import_card(file, session):
    data = await file.read(studio.MAX_IMPORT + 1)
    if len(data) > studio.MAX_IMPORT:
        raise HTTPException(413, '角色卡文件超过16MiB，请缩小封面或JSON')
    is_png = data[:8] == b"\x89PNG\r\n\x1a\n"
    try:
        if is_png:
            check_image(data)
            payload = read_card_png(data, max_json_bytes=studio.MAX_JSON)
        else:
            payload = json.loads(data.decode("utf-8-sig"))
        if len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()) > studio.MAX_JSON:
            raise ValueError('decoded character card too large')
        raw_fields = payload.get('data') if isinstance(payload, dict) and payload.get('spec') in ('chara_card_v2', 'chara_card_v3') else payload
        if isinstance(raw_fields, dict):
            for field in ('alternate_greetings', 'tags', 'extensions'):
                if raw_fields.get(field) is not None and not isinstance(raw_fields[field], dict if field == 'extensions' else list):
                    raise ValueError('invalid card collection field')
        fields = v2_to_fields(payload)
        # V1/V2/V3 parsing is not schema validation. Do this before any DB/media writes.
        studio.validate(session, fields)
    except (ValueError, UnicodeDecodeError, RecursionError, TypeError, OverflowError) as exc:
        raise HTTPException(422, '角色卡JSON或字段格式无效，请检查名称、文本、列表和扩展') from exc
    card = m.CharacterCard(**fields)
    card_data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    book_json = card_data.get("character_book") if isinstance(card_data, dict) else None
    if isinstance(book_json, dict) and book_json.get("entries"):
        try:
            if not isinstance(book_json['entries'], (list, dict)) or len(book_json['entries']) > 1000:
                raise ValueError('世界书条目超过1000或格式错误')
            book_data = lore_mod.book_from_json(dict(book_json, name=book_json.get("name") or f"{card.name} 的世界书"))
            # Validate the parsed book before creating a single row, not after commit.
            s.LorebookCreate.model_validate(book_data)
        except (ValueError, TypeError, OverflowError, RecursionError):
            raise HTTPException(422, '附带世界书格式或预算无效，角色卡和世界书均未导入') from None
        if book_data:
            entries = book_data.pop("entries")
            book = m.Lorebook(**book_data)
            book.entries = [m.LoreEntry(**e) for e in entries]
            session.add(book)
            session.flush()
            card.lorebook_id = book.id
    if is_png:
        from ..ingest import ingest
        avatar, _ = ingest(session, data, 'character-card.png', kind='reference', title=f'{card.name} · 角色卡封面')
        card.avatar_asset_id = avatar.id
    card.extensions = {**(card.extensions or {}), 'front_import_v1': {'origin': 'uploaded_card', 'linking_requires_review': True}}
    session.add(card)
    session.flush()
    versions.enable(session, card, '导入角色卡草稿')
    session.commit()
    session.refresh(card)
    if is_png:
        from ..ingest import make_thumb
        make_thumb(card.avatar_asset_id, data)
    return card


def check_image(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 16_000_000:
                raise HTTPException(422, '角色卡封面超过1600万像素，请选择较小图片；原图保留')
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(422, '角色卡封面损坏或格式不支持，原文件保留') from None


@io_router.get("/{card_id}/export.json")
def export_json(card_id: CardId, session: Session = Depends(get_session)) -> Response:
    card = get_or_404(session, m.CharacterCard, card_id)
    body = json.dumps(_v2(session, card), ensure_ascii=False, indent=2)
    return Response(
        body,
        media_type="application/json",
        headers={"Content-Disposition": _disposition(_filename(card.name, "json"))},
    )


@io_router.get("/{card_id}/export.png")
def export_png(card_id: CardId, session: Session = Depends(get_session)) -> Response:
    with studio.image_operation():
        return _export_png(card_id, session)


def _export_png(card_id, session):
    card = get_or_404(session, m.CharacterCard, card_id)
    base: bytes | None = None
    if card.avatar_asset_id:
        asset = session.get(m.Asset, card.avatar_asset_id)
        if not asset:
            raise HTTPException(409, '封面引用已失效，请选择其他素材或清除关联后导出')
        from .assets import _file_of
        from ..pathsafety import plain_path
        from ..models import ExternalAssetFile
        binding = session.get(ExternalAssetFile, asset.id) if not asset.file_path else None
        try:
            plain_path(get_settings().data_dir / asset.file_path if asset.file_path else binding.path if binding else '')
        except (ValueError, OSError):
            raise HTTPException(409, '封面路径不可用或是链接，未读取源文件') from None
        path = _file_of(asset)
        if path.stat().st_size > studio.MAX_IMPORT:
            raise HTTPException(422, '封面超过16MiB，请选择较小素材；JSON导出仍可使用')
        with path.open('rb') as stream:
            base = stream.read(studio.MAX_IMPORT + 1)
        if len(base) > studio.MAX_IMPORT:
            raise HTTPException(422, '读取时封面增大，未导出，请重新检查')
        if asset.sha256 and hashlib.sha256(base).hexdigest() != asset.sha256:
            raise HTTPException(409, '封面源文件内容已变化，未静默采用新版本')
        check_image(base)
    try:
        png = write_card_png(_v2(session, card), base)
    except (OSError, ValueError):
        raise HTTPException(422, '封面无法转换为PNG；原图保留，可改用JSON导出') from None
    return Response(
        png,
        media_type="image/png",
        headers={"Content-Disposition": _disposition(_filename(card.name, "png"))},
    )


@io_router.post("/from-character/{character_id}", response_model=s.CardRead, status_code=201)
def card_from_character(character_id: CardId, session: Session = Depends(get_session)) -> Any:
    """用百科里的角色条目生成一张角色卡草稿。"""
    char = get_or_404(session, m.Character, character_id)
    data = studio.from_character(session, char)
    studio.validate(session, data)
    card = m.CharacterCard(**data)
    session.add(card)
    session.flush()
    versions.enable(session, card, '由百科建立角色卡草稿')
    session.commit()
    session.refresh(card)
    return card
