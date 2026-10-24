"""数据模型。一个 SQLite 文件存全部元数据；二进制文件（图片/CG/模型）只存路径与哈希。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Float,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import event, text

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


def _tag_link(name: str, owner: str) -> Table:
    return Table(
        name,
        Base.metadata,
        Column(f"{owner}_id", ForeignKey(f"{owner}s.id", ondelete="CASCADE"), primary_key=True),
        Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )


asset_tags = _tag_link("asset_tags", "asset")
character_tags = _tag_link("character_tags", "character")
oc_profile_tags = _tag_link('oc_profile_tags','oc_profile')
world_tags = _tag_link("world_tags", "world")
prompt_tags = _tag_link("prompt_tags", "prompt")
sd_model_tags = _tag_link("sd_model_tags", "sd_model")
prompt_snippet_tags = _tag_link("prompt_snippet_tags", "prompt_snippet")
work_tags = _tag_link("work_tags", "work")
note_tags = _tag_link("note_tags", "note")
diagram_tags = _tag_link("diagram_tags", "diagram")
galgame_tags = _tag_link("galgame_tags", "galgame")

collection_assets = Table(
    "collection_assets",
    Base.metadata,
    Column("collection_id", ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
    Column("asset_id", ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
    Column("position", Integer, nullable=False, default=0, server_default="0"),
)


class Tag(Base):
    """标签。category 用来做“百科式”分面筛选：gender(男/女)、medium(动漫/游戏)、
    source(来源作品)、style(画风)、type(类型) 或自定义。"""

    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("category", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40), default="custom", index=True)
    color: Mapped[str | None] = mapped_column(String(16))
    # v0.3：别名（搜索与筛选时视同本名）与层级（父标签筛选时包含全部子标签）
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tags.id", ondelete="SET NULL"))


class Work(TimestampMixin, Base):
    """作品：动漫 / 游戏 / galgame / 小说 / 原创企划。CG 与收藏集挂在作品下。"""

    __tablename__ = "works"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="other")
    year: Mapped[int | None] = mapped_column(Integer)
    publisher: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[Tag]] = relationship(secondary=work_tags, lazy="selectin")


class World(TimestampMixin, Base):
    """世界观。content 为 Markdown 正文，AI 关系识别以此为语料。"""

    __tablename__ = "worlds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[Tag]] = relationship(secondary=world_tags, lazy="selectin")


class Asset(TimestampMixin, Base):
    """素材：自己的画、AI 生成图、绘画素材、小说、galgame CG 等。"""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="other", index=True)
    description: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)  # 小说 / 文本正文
    file_path: Mapped[str | None] = mapped_column(String(500))  # 相对数据目录 media/
    original_name: Mapped[str | None] = mapped_column(String(300))
    mime: Mapped[str | None] = mapped_column(String(100))
    size: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    source: Mapped[str | None] = mapped_column(String(500))
    work_date: Mapped[date | None] = mapped_column(Date, index=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    work_id: Mapped[int | None] = mapped_column(ForeignKey("works.id", ondelete="SET NULL"))
    world_id: Mapped[int | None] = mapped_column(ForeignKey("worlds.id", ondelete="SET NULL"))
    tags: Mapped[list[Tag]] = relationship(secondary=asset_tags, lazy="selectin")


class Live2DProfile(TimestampMixin, Base):
    """References original packages; never owns or deletes their files."""
    __tablename__ = 'live2d_profiles'
    id: Mapped[int] = mapped_column(primary_key=True)
    identity: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    source_path: Mapped[str] = mapped_column(Text)
    main: Mapped[str] = mapped_column(Text)
    scan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    creator: Mapped[str] = mapped_column(String(300), default='')
    source_url: Mapped[str] = mapped_column(String(2000), default='')
    license_notes: Mapped[str] = mapped_column(Text, default='')
    model_version: Mapped[str] = mapped_column(String(100), default='')
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    preference: Mapped[int] = mapped_column(Integer, default=0)
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default='')


class ChapterRevision(Base):
    """Append-only chapter plans. Parent uniqueness prevents concurrent lost updates."""
    __tablename__ = 'chapter_revisions'
    __table_args__ = (UniqueConstraint('asset_id', 'parent_revision'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey('assets.id', ondelete='CASCADE'), index=True)
    parent_revision: Mapped[int] = mapped_column(Integer, default=0)
    text_hash: Mapped[str] = mapped_column(String(64))
    chapters: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(String(500), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExternalAssetFile(Base):
    __tablename__ = 'external_asset_files'
    asset_id: Mapped[int] = mapped_column(ForeignKey('assets.id', ondelete='CASCADE'), primary_key=True)
    path: Mapped[str] = mapped_column(Text)
    root: Mapped[str] = mapped_column(Text)
    stamp: Mapped[list] = mapped_column(JSON)


class VersionHead(Base):
    """Opt-in histories; generation prevents SQLite reused IDs mixing histories."""
    __tablename__ = 'version_heads'
    kind: Mapped[str] = mapped_column(String(30), primary_key=True)
    entity_id: Mapped[int] = mapped_column(primary_key=True)
    generation: Mapped[str] = mapped_column(String(32))
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class VersionBlob(Base):
    __tablename__ = 'version_blobs'
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class EntityVersion(Base):
    __tablename__ = 'entity_versions'
    id: Mapped[int] = mapped_column(primary_key=True)
    generation: Mapped[str] = mapped_column(String(32), index=True)
    blob_sha: Mapped[str] = mapped_column(ForeignKey('version_blobs.sha256'))
    note: Mapped[str] = mapped_column(String(500), default='')
    source: Mapped[str] = mapped_column(String(100), default='manual')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RetainedMedia(Base):
    __tablename__ = 'retained_media'
    path: Mapped[str] = mapped_column(String(500), primary_key=True)


class ExtractionBatch(TimestampMixin, Base):
    __tablename__ = 'extraction_batches'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey('assets.id',ondelete='SET NULL'),index=True)
    asset_created_at: Mapped[str] = mapped_column(String(50))
    world_id: Mapped[int | None] = mapped_column(ForeignKey('worlds.id',ondelete='SET NULL'),index=True)
    work_id: Mapped[int | None] = mapped_column(ForeignKey('works.id',ondelete='SET NULL'),index=True)
    revision: Mapped[int] = mapped_column(Integer)
    text_hash: Mapped[str] = mapped_column(String(64))
    chapter_indices: Mapped[list[int]] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(300))
    model: Mapped[str] = mapped_column(String(200))
    endpoint_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20),default='queued')
    job_id: Mapped[str | None] = mapped_column(String(12))


class ExtractionUnit(Base):
    __tablename__ = 'extraction_units'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('extraction_batches.id'),index=True)
    chapter_index: Mapped[int] = mapped_column(Integer)
    chapter_title: Mapped[str] = mapped_column(String(300))
    start: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20),default='queued')
    result: Mapped[list[dict]] = mapped_column(JSON,default=list)
    error: Mapped[str] = mapped_column(String(300),default='')


class ExtractionApproval(Base):
    __tablename__ = 'extraction_approvals'
    __table_args__ = (UniqueConstraint('batch_id','candidate_name'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('extraction_batches.id'),index=True)
    candidate_name: Mapped[str] = mapped_column(String(200))
    character_id: Mapped[int | None] = mapped_column(ForeignKey('characters.id',ondelete='SET NULL'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)


class ExtractionEvidence(Base):
    __tablename__ = 'extraction_evidence'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('extraction_batches.id'),index=True)
    entity_kind: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[int] = mapped_column(Integer,index=True)
    entity_created_at: Mapped[str] = mapped_column(String(50))
    evidence: Mapped[dict] = mapped_column(JSON)


class WorldLabel(Base):
    __tablename__ = 'world_labels'
    __table_args__ = (UniqueConstraint('world_id','name'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    world_id: Mapped[int] = mapped_column(ForeignKey('worlds.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(80))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey('world_labels.id', ondelete='SET NULL'))


class WorldResource(TimestampMixin, Base):
    __tablename__ = 'world_resources'
    __table_args__ = (UniqueConstraint('world_id','entity_kind','entity_id'), UniqueConstraint('world_id','source_key'))
    id: Mapped[int] = mapped_column(primary_key=True)
    world_id: Mapped[int] = mapped_column(ForeignKey('worlds.id', ondelete='CASCADE'), index=True)
    entity_kind: Mapped[str] = mapped_column(String(30), default='asset')
    entity_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(80), default='resource')
    source_key: Mapped[str | None] = mapped_column(String(64))
    source_path: Mapped[str | None] = mapped_column(Text)
    storage_mode: Mapped[str] = mapped_column(String(20), default='reference')
    global_tag_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    label_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    preference: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default='')


class ProjectImport(TimestampMixin, Base):
    __tablename__ = 'project_imports'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    world_id: Mapped[int] = mapped_column(ForeignKey('worlds.id', ondelete='CASCADE'), index=True)
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default='queued')
    report_id: Mapped[str] = mapped_column(String(12))
    job_id: Mapped[str | None] = mapped_column(String(12))


class ProjectImportItem(Base):
    __tablename__ = 'project_import_items'
    __table_args__ = (UniqueConstraint('import_id','file_index'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[str] = mapped_column(ForeignKey('project_imports.id', ondelete='CASCADE'), index=True)
    file_index: Mapped[int] = mapped_column(Integer)
    selection: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    resource_id: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(String(500), default='')


@event.listens_for(Tag,'after_delete')
def _detach_archived_global_tag(_mapper,conn,target):
    conn.execute(text('''UPDATE world_resources SET global_tag_ids=(
        SELECT json_group_array(value) FROM json_each(world_resources.global_tag_ids) WHERE value!=:id)
        WHERE EXISTS (SELECT 1 FROM json_each(world_resources.global_tag_ids) WHERE value=:id)'''),{'id':target.id})


class Collection(TimestampMixin, Base):
    """收藏集：把素材按主题或按作品归档。"""

    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    work_id: Mapped[int | None] = mapped_column(ForeignKey("works.id", ondelete="SET NULL"))
    cover_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # 只读关系：按 collection_assets.position 排序。写入请用 collections.set_items()
    assets: Mapped[list[Asset]] = relationship(
        secondary=collection_assets,
        order_by=collection_assets.c.position,
        lazy="selectin",
        viewonly=True,
    )


class Character(TimestampMixin, Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    alias: Mapped[str | None] = mapped_column(String(300))
    gender: Mapped[str] = mapped_column(String(20), default="unknown")
    summary: Mapped[str | None] = mapped_column(Text)
    profile: Mapped[str | None] = mapped_column(Text)
    world_id: Mapped[int | None] = mapped_column(ForeignKey("worlds.id", ondelete="SET NULL"))
    work_id: Mapped[int | None] = mapped_column(ForeignKey("works.id", ondelete="SET NULL"))
    avatar_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )
    tags: Mapped[list[Tag]] = relationship(secondary=character_tags, lazy="selectin")


class Relation(TimestampMixin, Base):
    """角色关系网的一条边。ai_suggested=True 表示由 AI 识别、等待人工确认。"""

    __tablename__ = "relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    target_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(Text)
    bidirectional: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_suggested: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)


class OCProfile(TimestampMixin, Base):
    """Creative drafts linked to canonical encyclopedia characters, never file owners."""
    __tablename__='oc_profiles'
    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int | None] = mapped_column(ForeignKey('characters.id',ondelete='SET NULL'),unique=True,index=True)
    title: Mapped[str] = mapped_column(String(200))
    fields: Mapped[dict[str,str]] = mapped_column(JSON,default=dict)
    designs: Mapped[list[dict]] = mapped_column(JSON,default=list)
    references: Mapped[list[dict]] = mapped_column(JSON,default=list)
    source: Mapped[str] = mapped_column(String(2000),default='')
    cover_asset_id: Mapped[int | None] = mapped_column(ForeignKey('assets.id',ondelete='SET NULL'))
    favorite: Mapped[bool] = mapped_column(Boolean,default=False)
    stars: Mapped[int] = mapped_column(Integer,default=0)
    preference: Mapped[int] = mapped_column(Integer,default=0)
    notes: Mapped[str] = mapped_column(Text,default='')
    tags: Mapped[list[Tag]] = relationship(secondary=oc_profile_tags,lazy='selectin')


class OCStudy(TimestampMixin, Base):
    """Practice journal; source files remain ordinary assets in a shared collection."""
    __tablename__='oc_studies'
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey('oc_profiles.id',ondelete='SET NULL'),index=True)
    profile_identity: Mapped[str] = mapped_column(String(50))
    collection_id: Mapped[int | None] = mapped_column(ForeignKey('collections.id',ondelete='SET NULL'))
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str] = mapped_column(Text,default='')
    entries: Mapped[list[dict]] = mapped_column(JSON,default=list)


class ImageService(TimestampMixin, Base):
    """Explicit image API contract; a chat provider alone never implies image support."""
    __tablename__='image_services'
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey('ai_providers.id',ondelete='CASCADE'))
    name: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(200))
    legacy_b64: Mapped[bool] = mapped_column(Boolean,default=False)
    verified_at: Mapped[str | None] = mapped_column(String(50))


class OCGenerationBatch(TimestampMixin, Base):
    __tablename__='oc_generation_batches'
    id: Mapped[str] = mapped_column(String(40),primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey('oc_profiles.id',ondelete='SET NULL'),index=True)
    profile_identity: Mapped[str] = mapped_column(String(50))
    scope: Mapped[dict] = mapped_column(JSON)
    design_id: Mapped[str | None] = mapped_column(String(80))
    recipe: Mapped[dict] = mapped_column(JSON)
    job_id: Mapped[str | None] = mapped_column(String(40))


class SDModel(TimestampMixin, Base):
    """Stable Diffusion 模型登记。只存元数据与本地路径，模型文件本身永远不进仓库。"""

    __tablename__ = "sd_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="checkpoint")
    base_model: Mapped[str | None] = mapped_column(String(60))
    version: Mapped[str | None] = mapped_column(String(60))
    file_name: Mapped[str | None] = mapped_column(String(300))
    local_path: Mapped[str | None] = mapped_column(String(1000))
    sha256: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[int | None] = mapped_column(Integer)
    trigger_words: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    preview_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )
    # {"SHA256": ..., "AutoV1": ..., "AutoV2": ..., "AutoV3": ...}，与 Civitai / A1111 的叫法一致
    hashes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Civitai 匹配结果（来自联网查询或本地的 .civitai.info）
    civitai: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[Tag]] = relationship(secondary=sd_model_tags, lazy="selectin")


class Prompt(TimestampMixin, Base):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    positive: Mapped[str] = mapped_column(Text, default="")
    negative: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[Tag]] = relationship(secondary=prompt_tags, lazy="selectin")


class Generation(TimestampMixin, Base):
    """一次出图记录：提示词 × 模型 → 图片。用来做“同一提示词不同模型”的风格对比。"""

    __tablename__ = "generations"

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[int | None] = mapped_column(ForeignKey("prompts.id", ondelete="CASCADE"))
    model_id: Mapped[int | None] = mapped_column(ForeignKey("sd_models.id", ondelete="SET NULL"))
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    # 同一次出图任务（XY 网格）的批次号，以及这张图在网格里的坐标 {"x": {...}, "y": {...}}
    batch: Mapped[str | None] = mapped_column(String(40), index=True)
    xy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PromptSnippet(TimestampMixin, Base):
    """提示词片段：画风 / 服装 / 构图……可以一键组合成完整提示词。"""

    __tablename__ = "prompt_snippets"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(30), default="other", index=True)
    positive: Mapped[str] = mapped_column(Text, default="")
    negative: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    preview_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    tags: Mapped[list[Tag]] = relationship(secondary=prompt_snippet_tags, lazy="selectin")


class CharacterCard(TimestampMixin, Base):
    """AI 角色扮演角色卡，字段对齐 SillyTavern / TavernAI Character Card V2。"""

    __tablename__ = "character_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    personality: Mapped[str] = mapped_column(Text, default="")
    scenario: Mapped[str] = mapped_column(Text, default="")
    first_mes: Mapped[str] = mapped_column(Text, default="")
    mes_example: Mapped[str] = mapped_column(Text, default="")
    creator_notes: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    post_history_instructions: Mapped[str] = mapped_column(Text, default="")
    alternate_greetings: Mapped[list[str]] = mapped_column(JSON, default=list)
    card_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    creator: Mapped[str] = mapped_column(String(200), default="")
    character_version: Mapped[str] = mapped_column(String(60), default="")
    extensions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL")
    )
    # v0.5：角色卡自带的世界书（Character Card V2 的 character_book）
    lorebook_id: Mapped[int | None] = mapped_column(ForeignKey("lorebooks.id", ondelete="SET NULL"))
    avatar_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )


class ChatSession(TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("character_cards.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), default="新对话")
    user_name: Mapped[str] = mapped_column(String(80), default="User")
    # v0.5：消息是一棵树（重新生成 / 编辑都会产生分支），head_id 指向当前显示分支的最后一条
    head_id: Mapped[int | None] = mapped_column(Integer)
    lorebook_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    messages: Mapped[list["ChatMessage"]] = relationship(
        order_by="ChatMessage.id", cascade="all, delete-orphan", lazy="selectin"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))  # user / assistant / system
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    parent_id: Mapped[int | None] = mapped_column(Integer, index=True)
    # 生成信息：模型、激活的世界书条目、是否被中断等
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


# ---------------- v0.3 百科增强 ----------------
world_entry_tags = Table(
    "world_entry_tags",
    Base.metadata,
    Column("world_entry_id", ForeignKey("world_entries.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

character_assets = Table(
    "character_assets",
    Base.metadata,
    Column("character_id", ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
    Column("asset_id", ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
    Column("position", Integer, nullable=False, default=0, server_default="0"),
)


class WorldEntry(TimestampMixin, Base):
    """世界观条目：地点 / 组织 / 事件 / 物品 / 概念。
    parent_id 组成层级（例如 城市 > 街区 > 建筑）；事件用 date_label 显示、sort_key 排序生成时间线。"""

    __tablename__ = "world_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    world_id: Mapped[int] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="location", index=True)
    name: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("world_entries.id", ondelete="SET NULL"))
    date_label: Mapped[str | None] = mapped_column(String(100))
    sort_key: Mapped[float | None] = mapped_column()
    image_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    tags: Mapped[list[Tag]] = relationship(secondary=world_entry_tags, lazy="selectin")
    links: Mapped[list["EntryCharacter"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="EntryCharacter.id"
    )


class EntryCharacter(Base):
    """角色与世界观条目的关联：所属组织、参与事件、常驻地点……role 写具体身份。"""

    __tablename__ = "entry_characters"
    __table_args__ = (UniqueConstraint("entry_id", "character_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("world_entries.id", ondelete="CASCADE"))
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    role: Mapped[str | None] = mapped_column(String(100))


class Appearance(TimestampMixin, Base):
    """角色的出场作品（一个角色可以出现在多部作品里）。"""

    __tablename__ = "appearances"
    __table_args__ = (UniqueConstraint("character_id", "work_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"))
    role: Mapped[str | None] = mapped_column(String(100))  # 主角 / 配角 / 客串……
    note: Mapped[str | None] = mapped_column(Text)


class GraphLayout(TimestampMixin, Base):
    """关系网保存的布局：scope 为 "world:<id>" 或 "all"。positions = {角色id: {x, y}}。"""

    __tablename__ = "graph_layouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(60), unique=True)
    positions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    kind_colors: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)


# ---------------- v0.5 AI 角色与世界观智能 ----------------
class AIProviderConfig(TimestampMixin, Base):
    """在设置页里配置的 AI 服务（OpenAI 兼容接口）。API Key 只保存在本机数据库里，接口永远不会返回原文。"""

    __tablename__ = "ai_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(40), default="openai")
    base_url: Mapped[str] = mapped_column(String(500))
    api_key: Mapped[str | None] = mapped_column(Text)
    chat_model: Mapped[str] = mapped_column(String(200), default="")
    embedding_model: Mapped[str] = mapped_column(String(200), default="")
    vision_model: Mapped[str] = mapped_column(String(200), default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.8)
    max_tokens: Mapped[int | None] = mapped_column(Integer)
    timeout: Mapped[float] = mapped_column(Float, default=120.0)
    notes: Mapped[str | None] = mapped_column(Text)


class AppSetting(Base):
    """键值设置：对话 / 嵌入 / 打标签各自用哪个服务等。"""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class Lorebook(TimestampMixin, Base):
    """世界书（Lorebook / World Info）：关键词命中时把条目内容注入对话上下文。
    可以挂在世界观上（该世界观角色的对话自动使用），也可以作为角色卡的 character_book。"""

    __tablename__ = "lorebooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    world_id: Mapped[int | None] = mapped_column(ForeignKey("worlds.id", ondelete="SET NULL"), index=True)
    scan_depth: Mapped[int] = mapped_column(Integer, default=4)
    token_budget: Mapped[int] = mapped_column(Integer, default=1024)
    recursive: Mapped[bool] = mapped_column(Boolean, default=False)
    extensions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    entries: Mapped[list["LoreEntry"]] = relationship(
        back_populates="lorebook", cascade="all, delete-orphan", lazy="selectin",
        order_by="(LoreEntry.insertion_order, LoreEntry.id)",
    )


class LoreEntry(TimestampMixin, Base):
    __tablename__ = "lore_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    lorebook_id: Mapped[int] = mapped_column(ForeignKey("lorebooks.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    secondary_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    selective: Mapped[bool] = mapped_column(Boolean, default=False)
    content: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    constant: Mapped[bool] = mapped_column(Boolean, default=False)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    insertion_order: Mapped[int] = mapped_column(Integer, default=100)
    priority: Mapped[int] = mapped_column(Integer, default=10)
    position: Mapped[str] = mapped_column(String(20), default="before_char")  # before_char / after_char
    extensions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    lorebook: Mapped[Lorebook] = relationship(back_populates="entries")


class Embedding(Base):
    """语义检索用的向量。一条记录对应一个条目在某个嵌入模型下的向量（float32）。"""

    __tablename__ = "embeddings"
    __table_args__ = (UniqueConstraint("entity", "entity_id", "model"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(200), index=True)
    dim: Mapped[int] = mapped_column(Integer)
    vector: Mapped[bytes] = mapped_column(LargeBinary)
    text_hash: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Note(TimestampMixin, Base):
    """超级笔记本里的一页笔记：Markdown 正文（块编辑器编辑），可以嵌套成笔记本，可以引用任何素材。"""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True, default="无标题")
    icon: Mapped[str | None] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    pinned: Mapped[bool] = mapped_column(default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    work_id: Mapped[int | None] = mapped_column(ForeignKey("works.id", ondelete="SET NULL"))
    world_id: Mapped[int | None] = mapped_column(ForeignKey("worlds.id", ondelete="SET NULL"))
    cover_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    tags: Mapped[list[Tag]] = relationship(secondary=note_tags, lazy="selectin")


class Diagram(TimestampMixin, Base):
    """图表画布：流程图 / 节点工作流 / 关系草图。节点与连线按 Vue Flow 的结构存成 JSON。"""

    __tablename__ = "diagrams"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True, default="未命名图表")
    kind: Mapped[str] = mapped_column(String(32), default="flowchart")  # flowchart / workflow / mindmap / other
    description: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {"nodes": [...], "edges": [...], "viewport": {...}}
    pinned: Mapped[bool] = mapped_column(default=False)
    work_id: Mapped[int | None] = mapped_column(ForeignKey("works.id", ondelete="SET NULL"))
    world_id: Mapped[int | None] = mapped_column(ForeignKey("worlds.id", ondelete="SET NULL"))
    tags: Mapped[list[Tag]] = relationship(secondary=diagram_tags, lazy="selectin")

    @property
    def nodes(self) -> int:
        return len((self.data or {}).get("nodes") or [])

    @property
    def edges(self) -> int:
        return len((self.data or {}).get("edges") or [])


class Galgame(TimestampMixin, Base):
    """galgame 游戏库的一条。元数据来自 Bangumi / VNDB / 月幕（sources 里记着各来源的 id 与评分），
    用户手动改过的字段记在 overrides，重新拉取时不会被覆盖。CG 档案通过 work_id 挂在作品下。"""

    __tablename__ = "galgames"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    title_cn: Mapped[str | None] = mapped_column(String(300))
    original: Mapped[str | None] = mapped_column(String(300))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="wishlist", index=True)
    my_rating: Mapped[int | None] = mapped_column(Integer)
    play_minutes: Mapped[int] = mapped_column(Integer, default=0)
    started_on: Mapped[str | None] = mapped_column(String(10))
    finished_on: Mapped[str | None] = mapped_column(String(10))
    notes: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    developer: Mapped[str | None] = mapped_column(String(300))
    release_date: Mapped[str | None] = mapped_column(String(10))
    platforms: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    nsfw: Mapped[bool] = mapped_column(default=False)
    cover_url: Mapped[str | None] = mapped_column(String(1000))
    has_cover: Mapped[bool] = mapped_column(default=False)
    sources: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    characters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    links: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    overrides: Mapped[list[str]] = mapped_column(JSON, default=list)
    pinned: Mapped[bool] = mapped_column(default=False)
    work_id: Mapped[int | None] = mapped_column(ForeignKey("works.id", ondelete="SET NULL"))
    tags: Mapped[list[Tag]] = relationship(secondary=galgame_tags, lazy="selectin")


class GalgamePlay(Base):
    """一次游玩记录（手动记）：日期 + 分钟数 + 备注。添加 / 删除时同步增减 Galgame.play_minutes。"""

    __tablename__ = "galgame_plays"

    id: Mapped[int] = mapped_column(primary_key=True)
    galgame_id: Mapped[int] = mapped_column(ForeignKey("galgames.id", ondelete="CASCADE"), index=True)
    played_on: Mapped[str] = mapped_column(String(10), index=True)
    minutes: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
