from __future__ import annotations

import io
from typing import Any

from PIL import Image

MAX_THUMB_SOURCE = 40 * 1024 * 1024


def is_image(data: bytes | None) -> bool:
    if not data:
        return False
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        return True
    except Exception:
        return False


def clean(d: dict[str, Any]) -> dict[str, Any]:
    """去掉空值，方便前端直接列出。"""
    return {k: v for k, v in d.items() if v is not None and not (isinstance(v, (str, list, dict)) and not v)
            and not (type(v) is int and v == 0)}


def text(v: Any, limit: int = 500) -> str | None:
    if v is None:
        return None
    s = str(v).strip().replace("\x00", "")
    return s[:limit] or None
