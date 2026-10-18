"""Delete managed files only after the owning database transaction commits."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.orm import Session

from .config import get_settings

KEY = "front_pending_file_deletes"
logger = logging.getLogger(__name__)


def schedule_delete(session: Session, path: Path) -> None:
    root = get_settings().data_dir.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        return
    transaction = session.get_nested_transaction() or session.get_transaction()
    if transaction is None:
        raise RuntimeError("File cleanup requires an active transaction")
    session.info.setdefault(KEY, {}).setdefault(transaction, set()).add((root, path))


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    # A released savepoint is not a durable outer commit.
    if session.in_nested_transaction():
        return
    pending = session.info.pop(KEY, {})
    for paths in pending.values():
        for root, path in paths:
            try:
                if path.resolve().is_relative_to(root) and path.resolve() != root:
                    path.unlink(missing_ok=True)
            except OSError:
                # Preserve the committed DB result. A leftover managed file is
                # safer than reporting a failed delete after the DB committed.
                logger.warning("A managed file could not be cleaned up after commit")


@event.listens_for(Session, "after_soft_rollback")
def _after_rollback(session: Session, previous_transaction) -> None:
    pending = session.info.get(KEY, {})
    for transaction in list(pending):
        ancestor = transaction
        while ancestor is not None:
            if ancestor is previous_transaction:
                pending.pop(transaction, None)
                break
            ancestor = ancestor.parent
    if not pending:
        session.info.pop(KEY, None)


@event.listens_for(Session, "after_transaction_end")
def _after_transaction_end(session: Session, transaction) -> None:
    # close() can roll back without going through Session.rollback(); session
    # objects may be reused, so stale paths must never survive a root transaction.
    if transaction.parent is None:
        session.info.pop(KEY, None)
