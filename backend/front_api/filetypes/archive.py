"""压缩包：列出内容（zip / tar），识别“其实是一个 Live2D 或 3D 模型”的 zip，并从中按需读取单个文件。
只读取目录与少量条目，绝不解压到磁盘。"""

from __future__ import annotations

import posixpath
import tarfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import Analysis

EXT = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz"}
MAX_LIST = 400
MAX_ENTRY = 64 * 1024 * 1024
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
MODEL_PRIORITY = (".vrm", ".pmx", ".glb", ".gltf", ".fbx", ".obj", ".pmd")
SIG = {b"7z\xbc\xaf\x27\x1c": "7z", b"Rar!\x1a\x07": "rar"}


def _decode_name(info: zipfile.ZipInfo) -> str:
    """日文 / 中文 Windows 打的 zip 常常没有 UTF-8 标记，文件名按 cp437 读进来会乱码，这里尝试还原。"""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        raw = info.filename.encode("cp437")
    except UnicodeEncodeError:
        return info.filename
    for enc in ("utf-8", "shift_jis", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return info.filename


def zip_names(z: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    return {_decode_name(i): i for i in z.infolist() if not i.is_dir() and not _junk(_decode_name(i))}


def _junk(name: str) -> bool:
    base = posixpath.basename(name)
    return name.startswith("__MACOSX/") or base in (".DS_Store", "Thumbs.db", "desktop.ini")


def read_entry(path: Path, entry: str) -> bytes:
    with zipfile.ZipFile(path) as z:
        names = zip_names(z)
        info = names.get(entry)
        if info is None:  # 模型文件里的相对路径大小写 / 斜杠不一定一致
            low = entry.replace("\\", "/").lower()
            info = next((v for k, v in names.items() if k.lower() == low), None)
        if info is None:
            raise KeyError(entry)
        if info.file_size > MAX_ENTRY:
            raise ValueError("条目过大")
        return z.read(info)


def detect_bundle(path: Path) -> dict[str, Any] | None:
    """zip 里是 Live2D（*.model3.json 或 Cubism 2 的 model.json + .moc）或 3D 模型时，返回 {kind, main, root}。"""
    try:
        with zipfile.ZipFile(path) as z:
            names = list(zip_names(z))
    except zipfile.BadZipFile:
        return None
    low = [n.lower() for n in names]
    m3 = sorted((n for n, lo in zip(names, low) if lo.endswith(".model3.json")), key=len)
    if m3:
        return {"kind": "live2d", "main": m3[0], "root": posixpath.dirname(m3[0]), "cubism": 3}
    if any(lo.endswith(".moc") for lo in low):
        m2 = sorted((n for n, lo in zip(names, low) if lo.endswith(".json") and ("model" in posixpath.basename(lo))), key=len)
        if m2:
            return {"kind": "live2d", "main": m2[0], "root": posixpath.dirname(m2[0]), "cubism": 2}
    for ext in MODEL_PRIORITY:
        hits = sorted((n for n, lo in zip(names, low) if lo.endswith(ext)), key=len)
        # 一个压缩包里只有少数几个模型文件时才当作“模型包”；大量模型的合集按普通压缩包处理
        if hits and len(hits) <= 3:
            return {"kind": "model3d", "main": hits[0], "root": posixpath.dirname(hits[0]), "format": ext.lstrip(".")}
    return None


def _first_image(z: zipfile.ZipFile, names: dict[str, zipfile.ZipInfo]) -> bytes | None:
    for n in sorted(names):
        if n.lower().endswith(IMAGE_EXT) and names[n].file_size < 20 * 1024 * 1024:
            return z.read(names[n])
    return None


def analyze(path: Path, ext: str, out: Analysis) -> None:
    with path.open("rb") as fh:
        head = fh.read(8)
    for sig, fmt in SIG.items():
        if head.startswith(sig):
            out.meta.update({"format": fmt, "note": f"{fmt} 格式只记录文件信息；需要查看内容时请解压后再导入或改存为 zip"})
            return
    entries: list[dict[str, Any]] = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = zip_names(z)
            enc = any(i.flag_bits & 0x1 for i in names.values())
            for n, i in sorted(names.items()):
                entries.append({"name": n, "size": i.file_size, "packed": i.compress_size})
            if not enc:
                out.thumb = _first_image(z, names)
        out.meta.update({"format": "zip", "encrypted": enc})
    elif tarfile.is_tarfile(path):
        with tarfile.open(path) as t:
            members = [mm for mm in t.getmembers() if mm.isfile()]
            for mm in members:
                entries.append({"name": mm.name, "size": mm.size})
            img = next((mm for mm in sorted(members, key=lambda x: x.name) if mm.name.lower().endswith(IMAGE_EXT) and mm.size < 20 << 20), None)
            if img is not None and ext in (".tar",):  # 压缩的 tar 读单个条目要解压前面的全部内容，太慢，跳过
                f = t.extractfile(img)
                out.thumb = f.read() if f else None
        out.meta["format"] = "tar"
    else:
        out.meta["note"] = "无法识别的压缩格式，只记录文件信息"
        return
    out.meta["count"] = len(entries)
    out.meta["unpacked_size"] = sum(e["size"] for e in entries)
    out.meta["entries"] = entries[:MAX_LIST]
    out.meta["by_ext"] = _by_ext(entries)
    out.content = "\n".join(e["name"] for e in entries[:5000])


def _by_ext(entries: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in entries:
        ext = posixpath.splitext(e["name"])[1].lower().lstrip(".") or "无扩展名"
        out[ext] = out.get(ext, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1])[:12])
