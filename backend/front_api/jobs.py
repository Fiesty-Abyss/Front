"""Bounded lazy workers; restart-safe history, without automatic replay of AI calls."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from fastapi import HTTPException

MAX_JOBS = 200

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

class Cancelled(Exception):
    pass

class Job:
    def __init__(self, kind: str, title: str, total: int = 0):
        self.id = uuid.uuid4().hex[:12]
        self.kind, self.title, self.total = kind, title, total
        self.done, self.status = 0, "queued"
        self.message = None
        self.errors: list[str] = []
        self.result: dict[str, Any] = {}
        self.cancel_requested = False
        self.created_at, self.finished_at = now(), None
        self._manager = None
        self._saved_at = 0.0

    def step(self, message: str | None = None):
        self.done += 1
        if message:
            self.message = message
        self.check()
        if self._manager and time.monotonic() - self._saved_at >= .25:
            self._manager.save(self)

    def check(self):
        if self.cancel_requested:
            raise Cancelled()

    def to_dict(self):
        return {k: getattr(self, k) for k in (
            "id", "kind", "title", "status", "total", "done", "message",
            "result", "created_at", "finished_at",
        )} | {"errors": self.errors[-20:]}

class Manager:
    def __init__(self, path: Path, workers: int = 2, queue_size: int = 32):
        self.path, self.workers, self.queue_size = path, workers, queue_size
        self.lock = threading.RLock()
        self.executor = None
        self.closed = False
        self.jobs: dict[str, Job] = {}
        path.parent.mkdir(parents=True, exist_ok=True)
        # Separate ledger avoids deadlocking progress against a worker's open front.db transaction.
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, snapshot TEXT NOT NULL)")
            rows = db.execute("SELECT snapshot FROM jobs ORDER BY rowid DESC LIMIT ?", (MAX_JOBS + workers + queue_size,)).fetchall()
        for (raw,) in reversed(rows):
            record = json.loads(raw)
            job = Job(record["kind"], record["title"])
            job.__dict__.update(record)
            job._manager = self
            if job.status in ("queued", "running"):
                job.status, job.finished_at = "interrupted", now()
                job.message = "服务中断；已提交的数据保留。请检查结果后手动重试。"
                self.save(job)
            self.jobs[job.id] = job

    def save(self, job):
        with self.lock, sqlite3.connect(self.path, timeout=10) as db:
            db.execute("INSERT INTO jobs VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot",
                       (job.id, json.dumps(job.to_dict(), ensure_ascii=False)))
            job._saved_at = time.monotonic()

    def start(self, kind, title, total, fn):
        with self.lock:
            if self.closed:
                raise HTTPException(503, "后台任务服务正在关闭")
            active = sum(j.status in ("queued", "running") for j in self.jobs.values())
            if active >= self.workers + self.queue_size:
                raise HTTPException(429, "后台任务队列已满，请稍后重试")
            job = Job(kind, title, total)
            job._manager = self
            self.jobs[job.id] = job
            self.save(job)
            terminal = [j for j in self.jobs.values() if j.status not in ("queued", "running")]
            for old in terminal[:-MAX_JOBS]:
                del self.jobs[old.id]
                with sqlite3.connect(self.path) as db:
                    db.execute("DELETE FROM jobs WHERE id=?", (old.id,))
            if self.executor is None:
                self.executor = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="front-job")
            self.executor.submit(self.run, job, fn)
            return job

    def run(self, job, fn):
        job.status = "running"
        self.save(job)
        try:
            job.check()
            fn(job)
            job.status = "cancelled" if job.cancel_requested else "done"
        except Cancelled:
            job.status = "cancelled"
        except Exception as exc:
            job.status = "error"
            # Arbitrary remote exception text can contain credentials; never persist it.
            job.message = f"任务失败（{type(exc).__name__}）；请检查输入与服务状态"
        finally:
            job.finished_at = now()
            self.save(job)

    def shutdown(self):
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                if job.status in ("queued", "running"):
                    job.cancel_requested = True
        if self.executor:
            self.executor.shutdown(wait=True)

_manager: Manager | None = None

def configure(path: Path):
    global _manager
    if _manager:
        _manager.shutdown()
    _manager = Manager(path)
    return _manager

def manager():
    global _manager
    if _manager is None:
        from .config import get_settings
        _manager = Manager(get_settings().data_dir / "jobs.sqlite3")
    return _manager

def start(kind: str, title: str, total: int, fn: Callable[[Job], None]) -> Job:
    return manager().start(kind, title, total, fn)

def get(job_id: str) -> Job | None:
    return manager().jobs.get(job_id)

def listing(kind: str | None = None):
    mgr = manager()
    with mgr.lock:
        return [j.to_dict() for j in reversed(list(mgr.jobs.values())) if not kind or j.kind == kind]
