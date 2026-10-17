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
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
world_tags = _tag_link("world_tags", "world")
prompt_tags = _tag_link("prompt_tags", "prompt")
sd_model_tags = _tag_link("sd_model_tags", "sd_model")
work_tags = _tag_link("work_tags", "work")

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
    avatar_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )


class ChatSession(TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("character_cards.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), default="新对话")
    user_name: Mapped[str] = mapped_column(String(80), default="User")
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
