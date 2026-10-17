"""Live2D 模型：识别 Cubism 2（model.json + .moc）与 Cubism 3 / 4 / 5（*.model3.json + .moc3）。

读取模型描述文件里的贴图、动作、表情、物理等信息，以及 .moc3 文件头里的版本号；第一张贴图作为缩略图。
网页预览需要 Live2D 官方的 Cubism Core（专有许可，Front 不附带），见 docs/FILETYPES.md。"""

from __future__ import annotations

import io
import json
import posixpath
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from .archive import zip_names

if TYPE_CHECKING:
    from . import Analysis

EXT = {".moc3", ".moc"}
# .moc3 第 5 个字节是格式版本（Cubism SDK 文档里的 csmMocVersion）
MOC3_VERSION = {1: "3.0", 2: "3.3", 3: "4.0", 4: "4.2", 5: "5.0", 6: "5.3"}


def moc_version(head: bytes) -> str | None:
    if head[:4] == b"MOC3" and len(head) > 4:
        return f"Cubism {MOC3_VERSION.get(head[4], '未知')}（moc3 v{head[4]}）"
    if head[:3] == b"moc" and len(head) > 3:
        return f"Cubism 2（moc v{head[3]}）"
    return None


def analyze_single(path: Path, ext: str, out: Analysis) -> None:
    with path.open("rb") as fh:
        out.meta["cubism"] = moc_version(fh.read(8)) or "无法识别"
    out.meta["note"] = "只有 .moc 文件：请把整个模型文件夹（含 model3.json 与贴图）打包成 zip 或用批量导入，才能看到贴图与动作"


def _join(root: str, rel: str) -> str:
    return posixpath.normpath(posixpath.join(root, rel.replace("\\", "/"))) if rel else rel


def analyze_zip(path: Path, bundle: dict[str, Any], out: Analysis) -> None:
    root, main = bundle["root"], bundle["main"]
    with zipfile.ZipFile(path) as z:
        names = zip_names(z)
        lower = {k.lower(): k for k in names}

        def has(p: str) -> bool:
            return p.lower() in lower

        def read(p: str) -> bytes:
            return z.read(names[lower[p.lower()]])

        desc = json.loads(read(main).decode("utf-8-sig"))
        meta: dict[str, Any] = {"bundle": True, "main": main, "root": root}
        if bundle["cubism"] == 3:
            refs = desc.get("FileReferences") or {}
            moc = _join(root, refs.get("Moc", ""))
            textures = [_join(root, t) for t in refs.get("Textures") or []]
            motions = {g: [_join(root, mm.get("File", "")) for mm in lst] for g, lst in (refs.get("Motions") or {}).items()}
            expressions = [e.get("Name") or posixpath.basename(e.get("File", "")) for e in refs.get("Expressions") or []]
            meta.update({
                "physics": bool(refs.get("Physics")), "pose": bool(refs.get("Pose")), "display_info": bool(refs.get("DisplayInfo")),
                "user_data": bool(refs.get("UserData")),
                "groups": {g.get("Name"): len(g.get("Ids") or []) for g in desc.get("Groups") or [] if g.get("Name")},
                "hit_areas": [h.get("Name") or h.get("Id") for h in desc.get("HitAreas") or []],
            })
        else:
            moc = _join(root, desc.get("model", ""))
            textures = [_join(root, t) for t in desc.get("textures") or []]
            motions = {g: [_join(root, mm.get("file", "")) for mm in lst] for g, lst in (desc.get("motions") or {}).items()}
            expressions = [e.get("name") or posixpath.basename(e.get("file", "")) for e in desc.get("expressions") or []]
            meta.update({"physics": bool(desc.get("physics")), "pose": bool(desc.get("pose")),
                         "hit_areas": [h.get("name") or h.get("id") for h in desc.get("hit_areas") or []]})
        meta["cubism"] = moc_version(read(moc)[:8]) if moc and has(moc) else ("Cubism 3+" if bundle["cubism"] == 3 else "Cubism 2")
        tex_info = []
        for t in textures:
            item: dict[str, Any] = {"path": t}
            if has(t):
                try:
                    with Image.open(io.BytesIO(read(t))) as im:
                        item["size"] = f"{im.width}×{im.height}"
                except Exception:
                    pass
            tex_info.append(item)
        refs_all = [moc, *textures, *[f for lst in motions.values() for f in lst]]
        meta.update({
            "moc": moc, "textures": tex_info, "motions": {g: len(v) for g, v in motions.items()},
            "motion_files": {g: v[:30] for g, v in motions.items()}, "expressions": expressions[:60],
            "missing": [p for p in refs_all if p and not has(p)][:20], "files": len(names),
        })
        out.meta.update(meta)
        out.title = posixpath.basename(main).split(".")[0] or None
        if textures and has(textures[0]):
            out.thumb = _texture_thumb(read(textures[0]))


def _texture_thumb(data: bytes) -> bytes:
    """贴图是透明底的部件拼图，铺在深色底上做缩略图更好认。"""
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGBA")
        im.thumbnail((512, 512))
        bg = Image.new("RGBA", im.size, (30, 30, 44, 255))
        bg.alpha_composite(im)
        buf = io.BytesIO()
        bg.convert("RGB").save(buf, "PNG")
        return buf.getvalue()
