"""扫描本机的 SD 模型目录（SD WebUI / Forge / ComfyUI 的 models 文件夹），计算哈希并读取旁边的说明文件。
只读：模型文件不会被复制、移动或上传，数据库里只记路径与元数据。"""

from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path
from typing import Any, Callable

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
            if length > 16 * 1024 * 1024 or length + 8 > path.stat().st_size:
                return 0, {}
            header = json.loads(fh.read(length))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0, {}
    return (length, header) if isinstance(header, dict) else (0, {})


def safetensors_metadata(path: Path) -> dict[str, str]:
    _, header = read_safetensors_header(path)
    meta = header.get("__metadata__") or {}
    if not isinstance(meta, dict):
        return {}
    return {k: v for k, v in list(meta.items())[:64] if isinstance(v, str) and len(v) < 1000}


def compute_hashes(path: Path, check: Callable[[], None] = lambda: None) -> dict[str, str]:
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
            check()
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
    if meta.get("ss_network_module"):
        return "lycoris" if "lycoris" in str(meta["ss_network_module"]).lower() else "lora"
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
        if cand.is_file() and not cand.is_symlink() and cand.resolve().parent == path.resolve().parent:
            return cand
    return None


def read_sidecars(path: Path) -> dict[str, Any]:
    """读取模型旁边的说明文件：Civitai Helper 的 .civitai.info、SD WebUI 的 .json（用户元数据）。"""
    base = path.with_suffix("")
    out: dict[str, Any] = {}
    info = Path(str(base) + ".civitai.info")
    if info.is_file() and not info.is_symlink() and info.resolve().parent == path.resolve().parent and info.stat().st_size <= 2 * 1024 * 1024:
        try:
            out["civitai_info"] = json.loads(info.read_text("utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass
    user = Path(str(base) + ".json")
    if user.is_file() and not user.is_symlink() and user.resolve().parent == path.resolve().parent and user.stat().st_size <= 2 * 1024 * 1024:
        try:
            data = json.loads(user.read_text("utf-8"))
            if isinstance(data, dict):
                out["user_meta"] = data
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass
    return out


def describe(path: Path, root: Path, *, with_hash: bool = False, check: Callable[[], None] = lambda: None) -> dict[str, Any]:
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
        "hashes": compute_hashes(path, check) if with_hash else {},
        "diagnostics": diagnostics(path),
        "compatibility": "unverified",
    }
    return item


def model_roots(root: Path) -> list[Path]:
    """Unwrap an archive's same-name wrapper; restrict software installs to asset folders."""
    current = root
    for _ in range(3):
        child = current / current.name
        if (current / 'models').is_dir() or not child.is_dir() or child.is_symlink():
            break
        current = child
    if (current / 'models').is_dir():
        return [p for p in (current / 'models', current / 'embeddings',
                current / 'extensions/sd-webui-controlnet/models',
                current / 'extensions/sd-webui-additional-networks/models') if p.is_dir()]
    return [root]


def iter_model_files(root: Path, recursive: bool = True, check: Callable[[], None] = lambda: None) -> list[Path]:
    files: list[Path] = []
    boundary = root.resolve()
    for source in model_roots(root) if recursive else [root]:
        walker = os.walk(source) if recursive else [(str(source), [], [p.name for p in source.iterdir() if p.is_file()])]
        for dirpath, dirnames, filenames in walker:
            check()
            dirnames[:] = sorted(d for d in dirnames if not d.startswith('.') and d not in ('venv', 'node_modules', '__pycache__')
                                and not (Path(dirpath) / d).is_symlink() and (Path(dirpath) / d).resolve().is_relative_to(boundary))
            for name in sorted(filenames):
                p = Path(dirpath) / name
                if p.suffix.lower() in MODEL_EXT and not p.is_symlink() and p.resolve().is_relative_to(boundary):
                    files.append(p)
                    if len(files) > MAX_FILES:
                        raise ValueError('超过5000个模型文件，请选择更小的目录')
    return files


def diagnostics(path: Path) -> list[str]:
    """Header checks are not execution or a guarantee of engine compatibility."""
    if path.suffix.lower() != '.safetensors':
        return ['仅登记格式与元数据；未反序列化权重，架构与引擎兼容性待验证']
    length, header = read_safetensors_header(path)
    if not length:
        return ['无效或超过16MiB限制的 safetensors 头部']
    tensors = [v for k, v in header.items() if k != '__metadata__']
    if not tensors:
        return ['仅有元数据，未发现张量描述']
    size = path.stat().st_size - 8 - length
    for value in tensors:
        if not isinstance(value, dict):
            return ['张量描述结构异常']
        offsets = value.get('data_offsets')
        shape = value.get('shape')
        if not isinstance(offsets, list) or len(offsets) != 2 or any(type(v) is not int for v in offsets) or not 0 <= offsets[0] <= offsets[1] <= size:
            return ['张量数据偏移超出文件或格式异常']
        if not isinstance(shape, list) or any(type(v) is not int or v < 0 for v in shape):
            return ['张量形状异常']
    return ['头部与偏移已检查；未加载张量，运行兼容性待验证']
