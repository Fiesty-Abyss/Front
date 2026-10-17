"""Pydantic 输入/输出模型。Create 用于新增，Update 全部字段可选（PATCH 语义）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AssetKind = Literal["drawing", "ai_image", "material", "novel", "cg", "reference", "other"]
WorkKind = Literal["anime", "game", "galgame", "novel", "manga", "original", "other"]
Gender = Literal["male", "female", "other", "unknown"]
ModelKind = Literal["checkpoint", "lora", "lycoris", "vae", "embedding", "controlnet", "upscaler", "other"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Tag ----------
class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    category: str = Field(default="custom", max_length=40)
    color: str | None = None


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    category: str | None = None
    color: str | None = None


class TagRead(ORM):
    id: int
    name: str
    category: str
    color: str | None = None


class Timestamps(ORM):
    created_at: datetime
    updated_at: datetime


# ---------- Work ----------
class WorkBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: WorkKind = "other"
    year: int | None = None
    publisher: str | None = None
    url: str | None = None
    description: str | None = None


class WorkCreate(WorkBase):
    tag_ids: list[int] = []


class WorkUpdate(BaseModel):
    title: str | None = None
    kind: WorkKind | None = None
    year: int | None = None
    publisher: str | None = None
    url: str | None = None
    description: str | None = None
    tag_ids: list[int] | None = None


class WorkRead(WorkBase, Timestamps):
    id: int
    tags: list[TagRead] = []


# ---------- World ----------
class WorldBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    content: str | None = None


class WorldCreate(WorldBase):
    tag_ids: list[int] = []


class WorldUpdate(BaseModel):
    name: str | None = None
    summary: str | None = None
    content: str | None = None
    tag_ids: list[int] | None = None


class WorldRead(WorldBase, Timestamps):
    id: int
    tags: list[TagRead] = []


# ---------- Asset ----------
class AssetBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    kind: AssetKind = "other"
    description: str | None = None
    content: str | None = None
    source: str | None = None
    work_date: date | None = None
    meta: dict[str, Any] = {}
    work_id: int | None = None
    world_id: int | None = None


class AssetCreate(AssetBase):
    tag_ids: list[int] = []


class AssetUpdate(BaseModel):
    title: str | None = None
    kind: AssetKind | None = None
    description: str | None = None
    content: str | None = None
    source: str | None = None
    work_date: date | None = None
    meta: dict[str, Any] | None = None
    work_id: int | None = None
    world_id: int | None = None
    tag_ids: list[int] | None = None


class AssetRead(AssetBase, Timestamps):
    id: int
    file_path: str | None = None
    original_name: str | None = None
    mime: str | None = None
    size: int | None = None
    width: int | None = None
    height: int | None = None
    sha256: str | None = None
    tags: list[TagRead] = []


# ---------- Collection ----------
class CollectionBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    work_id: int | None = None


class CollectionCreate(CollectionBase):
    asset_ids: list[int] = []


class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    work_id: int | None = None
    asset_ids: list[int] | None = None


class CollectionRead(CollectionBase, Timestamps):
    id: int
    assets: list[AssetRead] = []


# ---------- Character ----------
class CharacterBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    alias: str | None = None
    gender: Gender = "unknown"
    summary: str | None = None
    profile: str | None = None
    world_id: int | None = None
    work_id: int | None = None
    avatar_asset_id: int | None = None


class CharacterCreate(CharacterBase):
    tag_ids: list[int] = []


class CharacterUpdate(BaseModel):
    name: str | None = None
    alias: str | None = None
    gender: Gender | None = None
    summary: str | None = None
    profile: str | None = None
    world_id: int | None = None
    work_id: int | None = None
    avatar_asset_id: int | None = None
    tag_ids: list[int] | None = None


class CharacterRead(CharacterBase, Timestamps):
    id: int
    tags: list[TagRead] = []


# ---------- Relation ----------
class RelationBase(BaseModel):
    source_id: int
    target_id: int
    kind: str = Field(min_length=1, max_length=60)
    description: str | None = None
    bidirectional: bool = True
    ai_suggested: bool = False
    confirmed: bool = True


class RelationCreate(RelationBase):
    pass


class RelationUpdate(BaseModel):
    source_id: int | None = None
    target_id: int | None = None
    kind: str | None = None
    description: str | None = None
    bidirectional: bool | None = None
    ai_suggested: bool | None = None
    confirmed: bool | None = None


class RelationRead(RelationBase, Timestamps):
    id: int


# ---------- SD Model ----------
class SDModelBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: ModelKind = "checkpoint"
    base_model: str | None = None
    version: str | None = None
    file_name: str | None = None
    local_path: str | None = None
    sha256: str | None = None
    size: int | None = None
    trigger_words: str | None = None
    source_url: str | None = None
    notes: str | None = None
    preview_asset_id: int | None = None


class SDModelCreate(SDModelBase):
    tag_ids: list[int] = []


class SDModelUpdate(BaseModel):
    name: str | None = None
    kind: ModelKind | None = None
    base_model: str | None = None
    version: str | None = None
    file_name: str | None = None
    local_path: str | None = None
    sha256: str | None = None
    size: int | None = None
    trigger_words: str | None = None
    source_url: str | None = None
    notes: str | None = None
    preview_asset_id: int | None = None
    tag_ids: list[int] | None = None


class SDModelRead(SDModelBase, Timestamps):
    id: int
    tags: list[TagRead] = []


# ---------- Prompt ----------
class PromptBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    positive: str = ""
    negative: str | None = None
    params: dict[str, Any] = {}
    notes: str | None = None


class PromptCreate(PromptBase):
    tag_ids: list[int] = []


class PromptUpdate(BaseModel):
    title: str | None = None
    positive: str | None = None
    negative: str | None = None
    params: dict[str, Any] | None = None
    notes: str | None = None
    tag_ids: list[int] | None = None


class PromptRead(PromptBase, Timestamps):
    id: int
    tags: list[TagRead] = []


# ---------- Generation ----------
class GenerationBase(BaseModel):
    prompt_id: int | None = None
    model_id: int | None = None
    asset_id: int | None = None
    params: dict[str, Any] = {}
    notes: str | None = None


class GenerationCreate(GenerationBase):
    pass


class GenerationUpdate(BaseModel):
    prompt_id: int | None = None
    model_id: int | None = None
    asset_id: int | None = None
    params: dict[str, Any] | None = None
    notes: str | None = None


class GenerationRead(GenerationBase, Timestamps):
    id: int


# ---------- Character Card ----------
class CardBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_mes: str = ""
    mes_example: str = ""
    creator_notes: str = ""
    system_prompt: str = ""
    post_history_instructions: str = ""
    alternate_greetings: list[str] = []
    card_tags: list[str] = []
    creator: str = ""
    character_version: str = ""
    extensions: dict[str, Any] = {}
    character_id: int | None = None
    avatar_asset_id: int | None = None


class CardCreate(CardBase):
    pass


class CardUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    personality: str | None = None
    scenario: str | None = None
    first_mes: str | None = None
    mes_example: str | None = None
    creator_notes: str | None = None
    system_prompt: str | None = None
    post_history_instructions: str | None = None
    alternate_greetings: list[str] | None = None
    card_tags: list[str] | None = None
    creator: str | None = None
    character_version: str | None = None
    extensions: dict[str, Any] | None = None
    character_id: int | None = None
    avatar_asset_id: int | None = None


class CardRead(CardBase, Timestamps):
    id: int


# ---------- Chat ----------
class ChatMessageRead(ORM):
    id: int
    role: str
    content: str
    created_at: datetime


class ChatSessionCreate(BaseModel):
    card_id: int
    title: str = "新对话"
    user_name: str = "User"


class ChatSessionRead(Timestamps):
    id: int
    card_id: int
    title: str
    user_name: str
    messages: list[ChatMessageRead] = []


class ChatSend(BaseModel):
    content: str = Field(min_length=1)


class Page(BaseModel):
    items: list[Any]
    total: int
