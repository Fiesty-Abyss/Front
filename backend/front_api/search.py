"""全文检索：SQLite FTS5 + trigram 分词（中文/日文按子串匹配）。

每次 flush 时自动同步索引，所以增删改即时可搜。少于 3 个字的查询（例如“诗梦”）
trigram 无法 MATCH，会自动退回 LIKE 子串匹配。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from . import models as m

FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5("
    "entity UNINDEXED, entity_id UNINDEXED, title, body, tokenize='trigram')"
)


def _tags(obj: Any) -> str:
    return " ".join(
        f"{t.category}:{t.name} {t.name} " + " ".join(t.aliases or []) for t in (getattr(obj, "tags", None) or [])
    )


def _join(*parts: Any) -> str:
    return "\n".join(str(p) for p in parts if p)


def _diagram_text(data: Any) -> str:
    """图表里每个节点的标题与说明、每条连线的文字都可以搜到。"""
    data = data or {}
    parts = []
    for n in data.get("nodes") or []:
        d = n.get("data") or {}
        parts += [d.get("label"), d.get("text")]
        parts += [f.get("label") for f in d.get("fields") or [] if isinstance(f, dict)]
    parts += [e.get("label") for e in data.get("edges") or []]
    return " ".join(str(p) for p in parts if p)


# 实体名 -> (标题, 正文)
SPEC: dict[type, tuple[str, Callable[[Any], str], Callable[[Any], str]]] = {
    m.Asset: ("asset", lambda o: o.title, lambda o: _join(o.description, o.content, o.source, o.original_name, _tags(o), (o.meta or {}).get("prompt"))),
    m.Character: ("character", lambda o: o.name, lambda o: _join(o.alias, o.summary, o.profile, _tags(o))),
    m.World: ("world", lambda o: o.name, lambda o: _join(o.summary, o.content, _tags(o))),
    m.Work: ("work", lambda o: o.title, lambda o: _join(o.publisher, o.description, _tags(o))),
    m.Prompt: ("prompt", lambda o: o.title, lambda o: _join(o.positive, o.negative, o.notes, _tags(o))),
    m.SDModel: ("sd_model", lambda o: o.name, lambda o: _join(o.base_model, o.file_name, o.trigger_words, o.notes, _tags(o))),
    m.CharacterCard: ("card", lambda o: o.name, lambda o: _join(o.description, o.personality, o.scenario, o.first_mes, " ".join(o.card_tags or []))),
    m.Collection: ("collection", lambda o: o.name, lambda o: _join(o.description)),
    m.PromptSnippet: ("snippet", lambda o: o.title, lambda o: _join(o.positive, o.negative, o.notes, _tags(o))),
    m.LoreEntry: ("lore", lambda o: o.title or "、".join(o.keys or []), lambda o: _join(" ".join(o.keys or []), " ".join(o.secondary_keys or []), o.content)),
    m.Note: ("note", lambda o: o.title, lambda o: _join(o.content, _tags(o))),
    m.Diagram: ("diagram", lambda o: o.title, lambda o: _join(o.description, _diagram_text(o.data), _tags(o))),
    m.WorldEntry: ("world_entry", lambda o: o.name, lambda o: _join(o.summary, o.content, o.date_label, _tags(o))),
    m.Galgame: ("galgame", lambda o: o.title, lambda o: _join(o.title_cn, o.original, " ".join(o.aliases or []), o.developer, o.description, o.notes, " ".join(o.source_tags or []), _tags(o))),
}


def ensure_fts(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(FTS_DDL))


def _delete(conn: Connection, entity: str, entity_id: int) -> None:
    conn.execute(
        text("DELETE FROM search_index WHERE entity=:e AND entity_id=:i"),
        {"e": entity, "i": entity_id},
    )


def _upsert(conn: Connection, obj: Any) -> None:
    entity, title_fn, body_fn = SPEC[type(obj)]
    _delete(conn, entity, obj.id)
    conn.execute(
        text("INSERT INTO search_index(entity, entity_id, title, body) VALUES (:e,:i,:t,:b)"),
        {"e": entity, "i": obj.id, "t": title_fn(obj) or "", "b": body_fn(obj) or ""},
    )


@event.listens_for(Session, "after_flush")
def _sync_index(session: Session, _ctx: Any) -> None:
    conn = session.connection()
    for obj in list(session.new) + list(session.dirty):
        if type(obj) in SPEC and obj.id is not None:
            _upsert(conn, obj)
    for obj in session.deleted:
        if type(obj) in SPEC and obj.id is not None:
            _delete(conn, SPEC[type(obj)][0], obj.id)


def rebuild(session: Session) -> int:
    conn = session.connection()
    conn.execute(text("DELETE FROM search_index"))
    n = 0
    for cls in SPEC:
        for obj in session.query(cls).all():
            _upsert(conn, obj)
            n += 1
    session.commit()
    return n


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(session: Session, q: str, entity: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    q = q.strip()
    if not q:
        return []
    params: dict[str, Any] = {"limit": limit}
    where_entity = ""
    if entity:
        where_entity = " AND entity = :entity"
        params["entity"] = entity
    if len(q) >= 3:
        params["q"] = '"' + q.replace('"', '""') + '"'
        sql = (
            "SELECT entity, entity_id, title, snippet(search_index, 3, '[', ']', '…', 12) AS snip "
            "FROM search_index WHERE search_index MATCH :q" + where_entity + " ORDER BY rank LIMIT :limit"
        )
    else:
        params["q"] = f"%{_escape_like(q)}%"
        sql = (
            "SELECT entity, entity_id, title, substr(body, 1, 80) AS snip FROM search_index "
            "WHERE (title LIKE :q ESCAPE '\\' OR body LIKE :q ESCAPE '\\')" + where_entity + " LIMIT :limit"
        )
    rows = session.connection().execute(text(sql), params).fetchall()
    return [
        {"entity": r[0], "id": int(r[1]), "title": r[2], "snippet": r[3]} for r in rows
    ]


def matching_ids(session: Session, entity: str, q: str) -> set[int]:
    return {hit["id"] for hit in search(session, q, entity=entity, limit=10_000)}
