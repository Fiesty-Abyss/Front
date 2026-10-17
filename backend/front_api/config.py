"""运行配置。所有用户数据（数据库、图片、小说、模型元数据）都放在数据目录里，
数据目录默认在仓库之外，绝不会被提交到 git。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _default_data_dir() -> Path:
    return Path(os.environ.get("FRONT_DATA_DIR", Path.home() / ".front-data")).expanduser()


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    ai_base_url: str | None
    ai_api_key: str | None
    ai_model: str | None
    max_upload_mb: int
    sd_webui_url: str | None = None
    comfyui_url: str | None = None
    sd_timeout: float = 600.0
    civitai_enabled: bool = True
    civitai_api_key: str | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "front.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def thumb_dir(self) -> Path:
        return self.data_dir / "thumbs"


@lru_cache
def get_settings() -> Settings:
    data_dir = _default_data_dir()
    return Settings(
        data_dir=data_dir,
        ai_base_url=os.environ.get("FRONT_AI_BASE_URL") or None,
        ai_api_key=os.environ.get("FRONT_AI_API_KEY") or None,
        ai_model=os.environ.get("FRONT_AI_MODEL") or None,
        max_upload_mb=int(os.environ.get("FRONT_MAX_UPLOAD_MB", "200")),
        sd_webui_url=(os.environ.get("FRONT_SD_WEBUI_URL") or "").rstrip("/") or None,
        comfyui_url=(os.environ.get("FRONT_COMFYUI_URL") or "").rstrip("/") or None,
        sd_timeout=float(os.environ.get("FRONT_SD_TIMEOUT", "600")),
        civitai_enabled=os.environ.get("FRONT_CIVITAI", "on").lower() not in ("0", "off", "false", "no"),
        civitai_api_key=os.environ.get("FRONT_CIVITAI_API_KEY") or None,
    )
