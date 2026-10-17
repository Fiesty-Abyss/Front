from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(url: str) -> Engine:
    global _engine, _SessionLocal
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return engine


def get_engine() -> Engine:
    assert _engine is not None, "init_engine() 尚未调用"
    return _engine


def get_session() -> Iterator[Session]:
    assert _SessionLocal is not None, "init_engine() 尚未调用"
    with _SessionLocal() as session:
        yield session


def new_session() -> Session:
    """后台任务（出图、批量计算哈希）在自己的线程里用独立的会话。"""
    assert _SessionLocal is not None, "init_engine() 尚未调用"
    return _SessionLocal()
