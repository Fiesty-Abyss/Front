"""Pydantic 输入/输出模型。Create 用于新增，Update 全部字段可选（PATCH 语义）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

AssetKind = Literal["drawing", "ai_image", "material", "novel", "cg", "reference", "other"]
WorkKind = Literal["anime", "game", "galgame", "novel", "manga", "original", "other"]
Gender = Literal["male", "female", "other", "unknown"]
ModelKind = Literal["checkpoint", "lora", "lycoris", "vae", "embedding", "controlnet", "upscaler", "hypernetwork", "text_encoder", "other"]
SnippetCategory = Literal["quality", "style", "character", "clothing", "pose", "composition", "background", "lighting", "negative", "other"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Tag ----------
class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    category: str = Field(default="custom", max_length=40)
    color: str | None = None
    aliases: list[str] = []
    parent_id: int | None = None


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    category: str | None = None
    color: str | None = None
    aliases: list[str] | None = None
    parent_id: int | None = None


class TagRead(ORM):
    id: int
    name: str
    category: str
    color: str | None = None
    aliases: list[str] = []
    parent_id: int | None = None


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
    cover_asset_id: int | None = None
    position: int = 0


class CollectionCreate(CollectionBase):
    asset_ids: list[int] = []


class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    work_id: int | None = None
    cover_asset_id: int | None = None
    position: int | None = None
    asset_ids: list[int] | None = None


class CollectionRead(CollectionBase, Timestamps):
    id: int
    assets: list[AssetRead] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_cover_id(self) -> int | None:
        """封面：手动指定的优先，否则用第一项。"""
        if self.cover_asset_id:
            return self.cover_asset_id
        return self.assets[0].id if self.assets else None


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
    hashes: dict[str, Any] = {}
    civitai: dict[str, Any] = {}
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
    batch: str | None = None
    xy: dict[str, Any] = {}


# ---------- Prompt snippet ----------
class SnippetBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: SnippetCategory = "other"
    positive: str = ""
    negative: str | None = None
    notes: str | None = None
    position: int = 0
    preview_asset_id: int | None = None


class SnippetCreate(SnippetBase):
    tag_ids: list[int] = []


class SnippetUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: SnippetCategory | None = None
    positive: str | None = None
    negative: str | None = None
    notes: str | None = None
    position: int | None = None
    preview_asset_id: int | None = None
    tag_ids: list[int] | None = None


class SnippetRead(SnippetBase, Timestamps):
    id: int
    tags: list[TagRead] = []


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
    lorebook_id: int | None = None


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
    lorebook_id: int | None = None


class CardRead(CardBase, Timestamps):
    id: int


# ---------- Chat ----------
class ChatMessageRead(ORM):
    id: int
    role: str
    content: str
    created_at: datetime
    parent_id: int | None = None
    meta: dict[str, Any] = {}
    sibling_ids: list[int] = []


class ChatSessionCreate(BaseModel):
    card_id: int
    title: str = "新对话"
    user_name: str = "User"


class ChatSessionRead(Timestamps):
    id: int
    card_id: int
    title: str
    user_name: str
    head_id: int | None = None
    lorebook_ids: list[int] = []
    total_messages: int = 0
    messages: list[ChatMessageRead] = []  # 当前分支：从第一条到 head


class ChatSend(BaseModel):
    content: str = Field(min_length=1)


class ChatSessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    user_name: str | None = Field(default=None, min_length=1, max_length=80)
    lorebook_ids: list[int] | None = None


class ChatGenerate(BaseModel):
    """content：发送新消息（接在 parent_id 或当前 head 后）；edit_id：编辑某条用户消息并另开分支；
    regenerate_id：重新生成某条 AI 回复（作为它的兄弟分支）；都不填：直接让 AI 接着当前 head 回复。"""
    content: str | None = None
    parent_id: int | None = None
    edit_id: int | None = None
    regenerate_id: int | None = None
    stream: bool = True


class ChatSelect(BaseModel):
    message_id: int


class ChatMessageUpdate(BaseModel):
    content: str = Field(min_length=1)


# ---------- v0.5 AI 服务 / 设置 ----------
class ProviderBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = "openai"
    base_url: str = Field(min_length=1, max_length=500)
    chat_model: str = ""
    embedding_model: str = ""
    vision_model: str = ""
    temperature: float = Field(default=0.8, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout: float = Field(default=120.0, gt=0, le=3600)
    notes: str | None = None


class ProviderCreate(ProviderBase):
    api_key: str | None = None


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    api_key: str | None = None  # 不传 = 不修改；传空字符串 = 清除
    chat_model: str | None = None
    embedding_model: str | None = None
    vision_model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout: float | None = Field(default=None, gt=0, le=3600)
    notes: str | None = None


class ProviderRead(ProviderBase, Timestamps):
    id: int
    api_key: str | None = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def api_key_set(self) -> bool:
        return bool(self.api_key)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def api_key_hint(self) -> str | None:
        k = self.api_key
        if not k:
            return None
        return f"{k[:3]}…{k[-4:]}" if len(k) > 10 else "已设置"


class SettingsUpdate(BaseModel):
    chat_provider_id: int | None = None
    embedding_backend: Literal["local", "provider"] | None = None
    embedding_provider_id: int | None = None
    tagger_backend: Literal["off", "webui", "vision"] | None = None
    vision_provider_id: int | None = None
    tagger_threshold: float | None = Field(default=None, ge=0, le=1)
    tagger_model: str | None = None
    user_name: str | None = Field(default=None, min_length=1, max_length=80)


# ---------- v0.5 世界书 ----------
LorePosition = Literal["before_char", "after_char"]


class LoreEntryBase(BaseModel):
    title: str = Field(default="", max_length=200)
    keys: list[str] = []
    secondary_keys: list[str] = []
    selective: bool = False
    content: str = ""
    enabled: bool = True
    constant: bool = False
    case_sensitive: bool = False
    insertion_order: int = 100
    priority: int = 10
    position: LorePosition = "before_char"
    extensions: dict[str, Any] = {}


class LoreEntryCreate(LoreEntryBase):
    pass


class LoreEntryUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    keys: list[str] | None = None
    secondary_keys: list[str] | None = None
    selective: bool | None = None
    content: str | None = None
    enabled: bool | None = None
    constant: bool | None = None
    case_sensitive: bool | None = None
    insertion_order: int | None = None
    priority: int | None = None
    position: LorePosition | None = None


class LoreEntryRead(LoreEntryBase, Timestamps):
    id: int
    lorebook_id: int


class LorebookBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    world_id: int | None = None
    scan_depth: int = Field(default=4, ge=0, le=100)
    token_budget: int = Field(default=1024, ge=0, le=100000)
    recursive: bool = False


class LorebookCreate(LorebookBase):
    entries: list[LoreEntryCreate] = []


class LorebookUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    world_id: int | None = None
    scan_depth: int | None = Field(default=None, ge=0, le=100)
    token_budget: int | None = Field(default=None, ge=0, le=100000)
    recursive: bool | None = None


class LorebookRead(LorebookBase, Timestamps):
    id: int
    entries: list[LoreEntryRead] = []


class LoreTest(BaseModel):
    text: str


# ---------- v0.5 AI 抽取 / 打标签 ----------
class ExtractRequest(BaseModel):
    asset_id: int | None = None
    text: str | None = None
    max_chunks: int = Field(default=20, ge=1, le=200)
    chunk_size: int = Field(default=3000, ge=500, le=20000)
    world_id: int | None = None


class ExtractedRelation(BaseModel):
    target: str
    kind: str = "相关"
    evidence: str = ""


class ExtractedCharacter(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = []
    gender: Gender = "unknown"
    summary: str = ""
    traits: list[str] = []
    appearance: str = ""
    relations: list[ExtractedRelation] = []
    existing_id: int | None = None


class ExtractApply(BaseModel):
    characters: list[ExtractedCharacter]
    world_id: int | None = None
    work_id: int | None = None
    tag_ids: list[int] = []
    relations: bool = True
    update_existing: bool = False
    source: str | None = None


class TaggerRun(BaseModel):
    asset_ids: list[int] = []
    only_untagged: bool = True
    apply: bool = True
    min_score: float = Field(default=0.5, ge=0, le=1)
    limit: int = Field(default=200, ge=1, le=5000)


# ---------- v0.3 世界观条目 / 出场作品 ----------
EntryKind = Literal["location", "organization", "event", "item", "concept"]


class EntryCharacterIn(BaseModel):
    character_id: int
    role: str | None = None


class EntryCharacterRead(ORM):
    character_id: int
    role: str | None = None


class WorldEntryBase(BaseModel):
    world_id: int
    kind: EntryKind = "location"
    name: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    content: str | None = None
    parent_id: int | None = None
    date_label: str | None = None
    sort_key: float | None = None
    image_asset_id: int | None = None


class WorldEntryCreate(WorldEntryBase):
    tag_ids: list[int] = []
    characters: list[EntryCharacterIn] = []


class WorldEntryUpdate(BaseModel):
    world_id: int | None = None
    kind: EntryKind | None = None
    name: str | None = None
    summary: str | None = None
    content: str | None = None
    parent_id: int | None = None
    date_label: str | None = None
    sort_key: float | None = None
    image_asset_id: int | None = None
    tag_ids: list[int] | None = None
    characters: list[EntryCharacterIn] | None = None


class WorldEntryRead(WorldEntryBase, Timestamps):
    id: int
    tags: list[TagRead] = []
    links: list[EntryCharacterRead] = []


class AppearanceBase(BaseModel):
    character_id: int
    work_id: int
    role: str | None = None
    note: str | None = None


class AppearanceCreate(AppearanceBase):
    pass


class AppearanceUpdate(BaseModel):
    role: str | None = None
    note: str | None = None


class AppearanceRead(AppearanceBase, Timestamps):
    id: int


class Page(BaseModel):
    items: list[Any]
    total: int
