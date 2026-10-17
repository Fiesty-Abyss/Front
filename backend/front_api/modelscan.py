"""扫描本机的 SD 模型目录（SD WebUI / Forge / ComfyUI 的 models 文件夹），计算哈希并读取旁边的说明文件。
只读：模型文件不会被复制、移动或上传，数据库里只记路径与元数据。"""

from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path
from typing import Any

MODEL_EXT = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf"}
PREVIEW_SUFFIXES = (".preview.png", ".preview.jpg", ".preview.jpeg", ".preview.webp", ".png", ".jpg", ".jpeg", ".webp")
MAX_FILES = 5000

# 目录名（小写）→ 模型类型。SD WebUI 与 ComfyUI 的默认目录名都在这里
DIR_KINDS: dict[str, str] = {
    "stable-diffusion": "checkpoint", "checkpoints": "checkpoint", "ckpt": "checkpoint", "unet": "checkpoint",
    "diffusion_models": "checkpoint",
    "lora": "lora", "loras": "lora",
    "lycoris": "lycoris", "locon": "lycoris", "lyco": "lycoris",
    "vae": "vae", "vae_approx": "vae",
    "embeddings": "embedding", "embedding": "embedding", "textual_inversion": "embedding",
    "controlnet": "controlnet", "control": "controlnet", "t2i_adapter": "controlnet",
    "esrgan": "upscaler", "realesrgan": "upscaler", "upscale_models": "upscaler", "swinir": "upscaler", "dat": "upscaler",
    "hypernetworks": "hypernetwork",
    "clip": "text_encoder", "text_encoders": "text_encoder",
}


def read_safetensors_header(path: Path) -> tuple[int, dict[str, Any]]:
    """返回 (头部长度, 头部 JSON)。不是合法 safetensors 时返回 (0, {})。"""
    try:
        with path.open("rb") as fh:
            head = fh.read(8)
            if len(head) < 8:
                return 0, {}
            (length,) = struct.unpack("<Q", head)
            if length > 100 * 1024 * 1024 or length > path.stat().st_size:
                return 0, {}
            header = json.loads(fh.read(length))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0, {}
    return (length, header) if isinstance(header, dict) else (0, {})


def safetensors_metadata(path: Path) -> dict[str, str]:
    _, header = read_safetensors_header(path)
    meta = header.get("__metadata__") or {}
    return {k: v for k, v in meta.items() if isinstance(v, str) and len(v) < 4000}


def compute_hashes(path: Path) -> dict[str, str]:
    """一次读取算出常见的几种模型哈希：
    - SHA256：完整文件
    - AutoV1：A1111 旧版 model hash（1 MiB 偏移处 64 KiB 的 SHA256 前 8 位）
    - AutoV2：SHA256 前 10 位（A1111 新版与 Civitai 使用）
    - AutoV3：safetensors 去掉头部后张量数据的 SHA256（Civitai / addnet 使用）"""
    full = hashlib.sha256()
    v3 = hashlib.sha256()
    header_len, _ = read_safetensors_header(path) if path.suffix.lower() == ".safetensors" else (0, {})
    skip = 8 + header_len if header_len else None
    pos = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            full.update(chunk)
            if skip is not None:
                end = pos + len(chunk)
                if end > skip:
                    v3.update(chunk[max(0, skip - pos):])
            pos += len(chunk)
        fh.seek(0x100000)
        v1 = hashlib.sha256(fh.read(0x10000)).hexdigest()[:8]
    sha = full.hexdigest()
    out = {"SHA256": sha.upper(), "AutoV1": v1.upper(), "AutoV2": sha[:10].upper()}
    if skip is not None:
        out["AutoV3"] = v3.hexdigest().upper()
    return out


def guess_base_model(meta: dict[str, Any]) -> str | None:
    raw = (meta.get("ss_base_model_version") or meta.get("modelspec.architecture") or meta.get("sd version") or "").lower()
    if not raw:
        return None
    for needle, label in (("flux", "Flux"), ("pony", "Pony"), ("illustrious", "Illustrious"), ("sd3", "SD3"),
                          ("sdxl", "SDXL"), ("xl", "SDXL"), ("v2", "SD2"), ("sd2", "SD2"), ("sd_v1", "SD1.5"),
                          ("v1", "SD1.5"), ("sd1", "SD1.5")):
        if needle in raw:
            return label
    return raw


def guess_kind(path: Path, root: Path, meta: dict[str, Any], size: int) -> str:
    try:
        parts = [p.lower() for p in path.relative_to(root).parts[:-1]]
    except ValueError:
        parts = []
    for part in reversed([root.name.lower(), *parts]):
        if part in DIR_KINDS:
            return DIR_KINDS[part]
    if meta.get("ss_network_module"):
        return "lycoris" if "lycoris" in meta["ss_network_module"] else "lora"
    if path.suffix.lower() == ".pt" and size < 1024 * 1024:
        return "embedding"
    return "checkpoint" if size > 1024 * 1024 * 1024 else "other"


def find_preview(path: Path) -> Path | None:
    base = path.with_suffix("")
    for suf in PREVIEW_SUFFIXES:
        cand = Path(str(base) + suf)
        if cand.is_file():
            return cand
    return None


def read_sidecars(path: Path) -> dict[str, Any]:
    """读取模型旁边的说明文件：Civitai Helper 的 .civitai.info、SD WebUI 的 .json（用户元数据）。"""
    base = path.with_suffix("")
    out: dict[str, Any] = {}
    info = Path(str(base) + ".civitai.info")
    if info.is_file():
        try:
            out["civitai_info"] = json.loads(info.read_text("utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass
    user = Path(str(base) + ".json")
    if user.is_file():
        try:
            data = json.loads(user.read_text("utf-8"))
            if isinstance(data, dict):
                out["user_meta"] = data
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass
    return out


def describe(path: Path, root: Path, *, with_hash: bool = False) -> dict[str, Any]:
    size = path.stat().st_size
    meta = safetensors_metadata(path) if path.suffix.lower() == ".safetensors" else {}
    side = read_sidecars(path)
    user = side.get("user_meta") or {}
    preview = find_preview(path)
    item: dict[str, Any] = {
        "file_name": path.name,
        "local_path": str(path),
        "relative": path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name,
        "size": size,
        "kind": guess_kind(path, root, meta, size),
        "base_model": guess_base_model({**meta, **({"sd version": user["sd version"]} if user.get("sd version") else {})}),
        "metadata": meta,
        "trigger_words": user.get("activation text") or None,
        "notes": user.get("description") or user.get("notes") or None,
        "preview": str(preview) if preview else None,
        "civitai_info": side.get("civitai_info"),
        "hashes": compute_hashes(path) if with_hash else {},
    }
    return item


def iter_model_files(root: Path, recursive: bool = True) -> list[Path]:
    files: list[Path] = []
    walker = os.walk(root) if recursive else [(str(root), [], [p.name for p in root.iterdir() if p.is_file()])]
    for dirpath, dirnames, filenames in walker:
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if p.suffix.lower() in MODEL_EXT:
                files.append(p)
                if len(files) >= MAX_FILES:
                    return files
    return files
