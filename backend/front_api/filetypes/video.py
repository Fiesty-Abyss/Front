"""视频：有 ffprobe / ffmpeg 时读取编码、分辨率、时长并截一帧做封面；没有就只记文件信息。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from .util import clean

if TYPE_CHECKING:
    from . import Analysis

EXT = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v", ".wmv", ".flv"}
BROWSER_PLAYABLE = {".mp4", ".webm", ".m4v", ".mov", ".ogv"}


def _probe(path: Path) -> dict:
    exe = shutil.which("ffprobe")
    if not exe:
        return {}
    r = subprocess.run([exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, timeout=30, check=False)
    return json.loads(r.stdout or b"{}")


def _frame(path: Path, at: float) -> bytes | None:
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    r = subprocess.run([exe, "-v", "error", "-ss", f"{at:.2f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=640:-2",
                        "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, timeout=60, check=False)
    return r.stdout or None


def analyze(path: Path, out: Analysis) -> None:
    out.meta["playable"] = path.suffix.lower() in BROWSER_PLAYABLE
    info = _probe(path)
    if not info:
        out.meta["probe"] = "未安装 ffprobe，只记录文件信息"
        return
    fmt = info.get("format") or {}
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), {})
    fps = None
    if v.get("avg_frame_rate") and "/" in v["avg_frame_rate"]:
        n, d = v["avg_frame_rate"].split("/")
        fps = round(int(n) / int(d), 2) if int(d or 0) else None
    duration = float(fmt.get("duration") or v.get("duration") or 0) or None
    tags = fmt.get("tags") or {}
    out.meta.update(clean({
        "duration": round(duration, 2) if duration else None, "resolution": f"{v['width']}×{v['height']}" if v.get("width") else None,
        "video_codec": v.get("codec_name"), "fps": fps, "audio_codec": a.get("codec_name"),
        "bitrate": round(int(fmt["bit_rate"]) / 1000) if fmt.get("bit_rate") else None,
        "container": fmt.get("format_long_name"), "title": tags.get("title"),
    }))
    if v:
        out.thumb = _frame(path, min(1.0, (duration or 0) / 3))
