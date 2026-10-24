"""代码与配置文本：识别语言、统计行数，正文存起来便于检索。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import Analysis

LANG = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript", ".vue": "xml", ".json": "json",
    ".yaml": "yaml", ".yml": "yaml", ".toml": "ini", ".ini": "ini", ".cfg": "ini", ".css": "css", ".scss": "scss",
    ".html": "xml", ".htm": "xml", ".xml": "xml", ".svg": "xml", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
    ".cs": "csharp", ".java": "java", ".go": "go", ".rs": "rust", ".lua": "lua", ".sh": "bash", ".bat": "dos",
    ".ps1": "powershell", ".sql": "sql", ".rb": "ruby", ".php": "php", ".kt": "kotlin", ".swift": "swift",
    ".rpy": "python", ".ks": "plaintext", ".tjs": "javascript", ".csv": "plaintext", ".tsv": "plaintext",
    ".log": "plaintext", ".srt": "plaintext", ".vtt":"plaintext", ".ass": "plaintext", ".lrc": "plaintext", ".glsl": "glsl", ".hlsl": "cpp",
}
EXT = set(LANG)
LABEL = {".rpy": "Ren'Py 脚本", ".ks": "KiriKiri 脚本", ".tjs": "TJS 脚本", ".srt": "字幕", ".ass": "字幕", ".lrc": "歌词"}
MAX = 2 * 1024 * 1024


def analyze(path: Path, ext: str, out: Analysis) -> None:
    from ..ingest import decode_text

    with path.open('rb') as stream:raw=stream.read(MAX)
    body = decode_text(raw)
    out.content = body
    out.meta.update({"language": LANG.get(ext, "plaintext"), "lines": body.count("\n") + 1,
                     "truncated": path.stat().st_size > MAX})
    if ext in LABEL:
        out.meta["label"] = LABEL[ext]
