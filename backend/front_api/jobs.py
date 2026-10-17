"""极简的后台任务：出图、批量计算哈希、批量匹配 Civitai 这类耗时操作放到线程里跑，
前端轮询 /api/jobs/{id} 看进度。任务状态只在内存里（重启后清空），产出的数据都已写进数据库。"""

from __future__ import annotations

import threading
import traceback
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable

_jobs: OrderedDict[str, "Job"] = OrderedDict()
_lock = threading.Lock()
MAX_JOBS = 200


class Cancelled(Exception):
    pass


class Job:
    def __init__(self, kind: str, title: str, total: int = 0):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title
        self.total = total
        self.done = 0
        self.status = "queued"  # queued / running / done / error / cancelled
        self.message: str | None = None
        self.errors: list[str] = []
        self.result: dict[str, Any] = {}
        self.cancel_requested = False
        self.created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.finished_at: str | None = None

    def step(self, message: str | None = None) -> None:
        self.done += 1
        if message:
            self.message = message
        self.check()

    def check(self) -> None:
        if self.cancel_requested:
            raise Cancelled()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "title": self.title, "status": self.status, "total": self.total,
            "done": self.done, "message": self.message, "errors": self.errors[-20:], "result": self.result,
            "created_at": self.created_at, "finished_at": self.finished_at,
        }


def start(kind: str, title: str, total: int, fn: Callable[[Job], None]) -> Job:
    job = Job(kind, title, total)
    with _lock:
        _jobs[job.id] = job
        while len(_jobs) > MAX_JOBS:
            _jobs.popitem(last=False)

    def run() -> None:
        job.status = "running"
        try:
            fn(job)
            job.status = "cancelled" if job.cancel_requested else "done"
        except Cancelled:
            job.status = "cancelled"
        except Exception as exc:  # noqa: BLE001 - 任务失败要记录下来给前端看
            job.status = "error"
            job.message = str(exc) or exc.__class__.__name__
            job.errors.append(traceback.format_exc(limit=3))
        finally:
            job.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    threading.Thread(target=run, name=f"front-job-{job.id}", daemon=True).start()
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def listing(kind: str | None = None) -> list[dict[str, Any]]:
    return [j.to_dict() for j in reversed(_jobs.values()) if not kind or j.kind == kind]
