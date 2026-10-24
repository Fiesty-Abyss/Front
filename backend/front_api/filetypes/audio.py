"""音频：用 tinytag（MIT）读取标签、时长、码率与内嵌封面。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from tinytag import TinyTag

from .util import clean, is_image, text

if TYPE_CHECKING:
    from . import Analysis

EXT = {".mp3", ".flac", ".ogg", ".oga", ".opus", ".wav", ".m4a", ".aac", ".wma", ".aiff", ".aif"}


def analyze(path: Path, out: Analysis,cover=True) -> None:
    # An unusually large ID3 tag must not allocate an unbounded embedded image/text frame.
    with path.open('rb') as stream:head=stream.read(10)
    oversized=head[:3]==b'ID3' and len(head)==10 and sum((b&127)<<(7*(3-i)) for i,b in enumerate(head[6:10]))>16*1024*1024
    tag = TinyTag.get(str(path), image=cover and not oversized,tags=not oversized)
    out.meta['format']=path.suffix.lstrip('.').upper()
    if oversized:out.meta['note']='ID3标签超过16MiB，仅提取音频技术信息，不读取封面与文本标签'
    out.meta.update(clean({
        "title": text(tag.title), "artist": text(tag.artist), "album": text(tag.album),
        "albumartist": text(tag.albumartist), "composer": text(tag.composer), "genre": text(tag.genre),
        "year": text(tag.year, 20), "track": tag.track, "track_total": tag.track_total, "disc": tag.disc,
        "comment": text(tag.comment, 1000),
        "duration": round(tag.duration, 2) if tag.duration else None,
        "bitrate": round(tag.bitrate) if tag.bitrate else None,
        "samplerate": tag.samplerate, "channels": tag.channels, "bitdepth": tag.bitdepth,
    }))
    if tag.title:
        out.title = text(tag.title, 200)
    img = tag.images.any if tag.images else None
    if img is not None and is_image(img.data):
        out.thumb = img.data
        out.meta["cover"] = img.mime_type or "image"
    lyrics = None
    try:
        lyrics = (tag.other or {}).get("lyrics")
    except Exception:
        pass
    if lyrics:
        out.content = "\n".join(lyrics) if isinstance(lyrics, list) else str(lyrics)
