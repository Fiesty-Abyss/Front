"""3D 模型：glTF / GLB / VRM（含 VRM 0.x 与 1.0 的作者、许可信息与缩略图）、OBJ、FBX、PMX / PMD（MMD）。

只解析文件头与描述信息，不执行任何内容。预览在浏览器里用 three.js 完成。"""

from __future__ import annotations

import json
import posixpath
import re
import struct
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .archive import zip_names
from .util import clean, is_image, text

if TYPE_CHECKING:
    from . import Analysis

EXT = {".glb", ".gltf", ".vrm", ".obj", ".fbx", ".pmx", ".pmd"}
FORMAT = {".glb": "glTF 二进制", ".gltf": "glTF", ".vrm": "VRM", ".obj": "Wavefront OBJ", ".fbx": "Autodesk FBX",
          ".pmx": "MMD PMX", ".pmd": "MMD PMD"}
PREVIEWABLE = {".glb", ".gltf", ".vrm", ".obj", ".fbx", ".pmx"}


# ── glTF / GLB / VRM ──
def split_glb(data: bytes) -> tuple[dict[str, Any], bytes]:
    magic, version, _ = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError("不是 GLB 文件")
    off, doc, binc = 12, None, b""
    while off + 8 <= len(data):
        length, ctype = struct.unpack_from("<I4s", data, off)
        chunk = data[off + 8: off + 8 + length]
        if ctype == b"JSON":
            doc = json.loads(chunk.decode("utf-8"))
        elif ctype == b"BIN\x00":
            binc = chunk
        off += 8 + length
    if doc is None:
        raise ValueError("GLB 缺少 JSON 块")
    doc.setdefault("_glb_version", version)
    return doc, binc


def _image_from_glb(doc: dict[str, Any], binc: bytes, image_index: int | None) -> bytes | None:
    images = doc.get("images") or []
    if image_index is None or not (0 <= image_index < len(images)):
        return None
    bv = images[image_index].get("bufferView")
    views = doc.get("bufferViews") or []
    if bv is None or bv >= len(views):
        return None
    v = views[bv]
    start = v.get("byteOffset", 0)
    data = binc[start: start + v.get("byteLength", 0)]
    return data if is_image(data) else None


def gltf_meta(doc: dict[str, Any]) -> dict[str, Any]:
    acc = doc.get("accessors") or []
    verts = tris = 0
    for mesh in doc.get("meshes") or []:
        for p in mesh.get("primitives") or []:
            pos = (p.get("attributes") or {}).get("POSITION")
            if isinstance(pos, int) and pos < len(acc):
                verts += acc[pos].get("count", 0)
            idx = p.get("indices")
            if isinstance(idx, int) and idx < len(acc) and p.get("mode", 4) == 4:
                tris += acc[idx].get("count", 0) // 3
    asset = doc.get("asset") or {}
    return clean({
        "generator": text(asset.get("generator"), 120), "gltf_version": asset.get("version"),
        "meshes": len(doc.get("meshes") or []), "materials": len(doc.get("materials") or []),
        "textures": len(doc.get("textures") or []), "nodes": len(doc.get("nodes") or []),
        "skins": len(doc.get("skins") or []), "animations": [a.get("name") or f"动画 {i + 1}" for i, a in enumerate(doc.get("animations") or [])][:40],
        "vertices": verts, "triangles": tris, "extensions": (doc.get("extensionsUsed") or [])[:20],
        "external_buffers": [b["uri"] for b in doc.get("buffers") or [] if b.get("uri") and not b["uri"].startswith("data:")][:10],
    })


def vrm_meta(doc: dict[str, Any]) -> tuple[dict[str, Any], int | None]:
    ext = doc.get("extensions") or {}
    if "VRMC_vrm" in ext:
        mm = ext["VRMC_vrm"].get("meta") or {}
        return clean({
            "vrm": "1.0", "name": text(mm.get("name")), "model_version": text(mm.get("version")),
            "authors": [text(a) for a in mm.get("authors") or []][:10], "copyright": text(mm.get("copyrightInformation")),
            "contact": text(mm.get("contactInformation")), "references": [text(r) for r in mm.get("references") or []][:10],
            "license_url": text(mm.get("licenseUrl")), "avatar_permission": mm.get("avatarPermission"),
            "commercial_usage": mm.get("commercialUsage"), "allow_redistribution": mm.get("allowRedistribution"),
            "modification": mm.get("modification"), "credit_notation": mm.get("creditNotation"),
            "allow_violent": mm.get("allowExcessivelyViolentUsage"), "allow_sexual": mm.get("allowExcessivelySexualUsage"),
        }), mm.get("thumbnailImage")
    if "VRM" in ext:
        mm = ext["VRM"].get("meta") or {}
        tex = mm.get("texture")
        image = None
        if isinstance(tex, int) and tex < len(doc.get("textures") or []):
            image = doc["textures"][tex].get("source")
        return clean({
            "vrm": "0.x", "name": text(mm.get("title")), "model_version": text(mm.get("version")),
            "authors": [text(mm.get("author"))] if mm.get("author") else [], "contact": text(mm.get("contactInformation")),
            "references": [text(mm.get("reference"))] if mm.get("reference") else [], "license": text(mm.get("licenseName")),
            "license_url": text(mm.get("otherLicenseUrl")), "avatar_permission": mm.get("allowedUserName"),
            "commercial_usage": mm.get("commercialUssageName"), "allow_violent": mm.get("violentUssageName"),
            "allow_sexual": mm.get("sexualUssageName"),
        }), image
    return {}, None


def _analyze_gltf_doc(doc: dict[str, Any], binc: bytes, out: Analysis) -> None:
    out.meta.update(gltf_meta(doc))
    vrm, thumb_idx = vrm_meta(doc)
    if vrm:
        out.meta["vrm_meta"] = vrm
        out.meta["format"] = f"VRM {vrm['vrm']}"
        if vrm.get("name"):
            out.title = vrm["name"]
        out.thumb = _image_from_glb(doc, binc, thumb_idx)


# ── OBJ ──
def obj_meta(data: bytes) -> dict[str, Any]:
    v = f = groups = 0
    mtllib: list[str] = []
    materials: set[str] = set()
    for line in data.splitlines():
        if line.startswith(b"v "):
            v += 1
        elif line.startswith(b"f "):
            f += 1
        elif line.startswith((b"o ", b"g ")):
            groups += 1
        elif line.startswith(b"mtllib "):
            mtllib.append(line[7:].decode("utf-8", "replace").strip())
        elif line.startswith(b"usemtl "):
            materials.add(line[7:].decode("utf-8", "replace").strip())
    return clean({"vertices": v, "faces": f, "groups": groups, "mtllib": mtllib[:5], "materials": len(materials)})


# ── FBX ──
def fbx_meta(head: bytes) -> dict[str, Any]:
    if head.startswith(b"Kaydara FBX Binary  \x00"):
        ver = struct.unpack_from("<I", head, 23)[0]
        return {"encoding": "二进制", "fbx_version": f"{ver // 1000}.{ver % 1000 // 100}", "previewable": ver >= 7000}
    m = re.search(rb"FBX (\d+)\.(\d+)", head[:200])
    if m:
        return {"encoding": "ASCII", "fbx_version": f"{int(m.group(1))}.{int(m.group(2))}", "previewable": int(m.group(1)) >= 7}
    return {"encoding": "未知"}


# ── PMX / PMD（MMD）──
class _Reader:
    def __init__(self, data: bytes, off: int = 0):
        self.d, self.o = data, off

    def take(self, n: int) -> bytes:
        b = self.d[self.o: self.o + n]
        if len(b) < n:
            raise ValueError("文件被截断")
        self.o += n
        return b

    def i(self, size: int = 4, signed: bool = True) -> int:
        fmt = {1: "b", 2: "h", 4: "i"}[size]
        return struct.unpack("<" + (fmt if signed else fmt.upper()), self.take(size))[0]

    def f(self, n: int = 1) -> tuple[float, ...]:
        return struct.unpack(f"<{n}f", self.take(4 * n))


def pmx_meta(data: bytes) -> dict[str, Any]:
    r = _Reader(data)
    if r.take(4) != b"PMX ":
        raise ValueError("不是 PMX 文件")
    version = round(r.f()[0], 1)
    g = r.take(r.i(1, False))
    enc = "utf-16-le" if g[0] == 0 else "utf-8"
    add_uv, vsz, tsz, bsz = g[1], g[2], g[3], g[5]

    def s() -> str:
        return r.take(r.i()).decode(enc, "replace")

    name, name_en, comment, comment_en = s(), s(), s(), s()
    nv = r.i()
    for _ in range(nv):
        r.take(32 + 16 * add_uv)
        w = r.i(1, False)
        r.take({0: bsz, 1: bsz * 2 + 4, 2: bsz * 4 + 16, 3: bsz * 2 + 4 + 36, 4: bsz * 4 + 16}[w] + 4)
    nidx = r.i()
    r.take(nidx * vsz)
    textures = [s().replace("\\", "/") for _ in range(r.i())]
    mats = []
    for _ in range(r.i()):
        mname = s()
        s()
        r.take(16 + 12 + 4 + 12 + 1 + 16 + 4)
        r.take(tsz * 2 + 1)
        toon_shared = r.i(1, False)
        r.take(1 if toon_shared else tsz)
        s()
        r.i()
        mats.append(mname)
    bones = r.i()
    return clean({"pmx_version": version, "model_name": name, "model_name_en": name_en, "comment": text(comment, 2000),
                  "comment_en": text(comment_en, 2000), "vertices": nv, "triangles": nidx // 3, "textures": textures[:60],
                  "materials": len(mats), "material_names": mats[:60], "bones": bones})


def pmd_meta(data: bytes) -> dict[str, Any]:
    if data[:3] != b"Pmd":
        raise ValueError("不是 PMD 文件")
    name = data[7:27].split(b"\x00")[0].decode("shift_jis", "replace")
    comment = data[27:283].split(b"\x00")[0].decode("shift_jis", "replace")
    nv = struct.unpack_from("<I", data, 283)[0]
    return clean({"pmd_version": round(struct.unpack_from("<f", data, 3)[0], 1), "model_name": name, "comment": text(comment, 2000), "vertices": nv,
                  "note": "PMD 是 MMD 的旧格式，只显示信息；用 PMX Editor 转为 PMX 后可以预览"})


def _analyze_bytes(data: bytes, ext: str, out: Analysis) -> None:
    out.meta["format"] = FORMAT[ext]
    out.meta["previewable"] = ext in PREVIEWABLE
    if ext in (".glb", ".vrm"):
        doc, binc = split_glb(data)
        _analyze_gltf_doc(doc, binc, out)
    elif ext == ".gltf":
        _analyze_gltf_doc(json.loads(data.decode("utf-8-sig")), b"", out)
    elif ext == ".obj":
        out.meta.update(obj_meta(data))
    elif ext == ".fbx":
        out.meta.update(fbx_meta(data[:400]))
        out.meta["previewable"] = out.meta.get("previewable", False)
    elif ext == ".pmx":
        mm = pmx_meta(data)
        out.meta.update(mm)
        if mm.get("model_name"):
            out.title = mm["model_name"]
    elif ext == ".pmd":
        mm = pmd_meta(data)
        out.meta.update(mm)
        if mm.get("model_name"):
            out.title = mm["model_name"]


def analyze(path: Path, ext: str, out: Analysis) -> None:
    _analyze_bytes(path.read_bytes(), ext, out)
    if ext == ".gltf" and out.meta.get("external_buffers"):
        out.meta["note"] = "这个 .gltf 引用了外部文件（.bin / 贴图）：请把整个文件夹打包成 zip 或用批量导入，才能预览"
        out.meta["previewable"] = False
    if ext == ".obj" and out.meta.get("mtllib"):
        out.meta["note"] = "材质文件（.mtl）和贴图不在一起时只显示白模；打包成 zip 可以带上材质"


def analyze_zip(path: Path, bundle: dict[str, Any], out: Analysis) -> None:
    with zipfile.ZipFile(path) as z:
        names = zip_names(z)
        main = bundle["main"]
        info = names[main]
        if info.file_size > 512 * 1024 * 1024:
            raise ValueError("模型文件过大")
        ext = posixpath.splitext(main)[1].lower()
        _analyze_bytes(z.read(info), ext, out)
        out.meta.update({"bundle": True, "main": main, "root": bundle["root"], "files": len(names)})
        if ext == ".pmx" and out.meta.get("textures"):
            low = {k.lower() for k in names}
            out.meta["missing"] = [t for t in out.meta["textures"]
                                   if posixpath.normpath(posixpath.join(bundle["root"], t)).lower() not in low][:20]
        if not out.thumb:  # 包里自带的预览图（常见于模型发布包）
            for n in sorted(names, key=len):
                b = posixpath.basename(n).lower()
                if re.match(r"(thumb|thumbnail|preview|cover|icon|サムネ)", b) and b.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    data = z.read(names[n])
                    if is_image(data):
                        out.thumb = data
                        break
    if not out.title:
        out.title = posixpath.splitext(posixpath.basename(bundle["main"]))[0]
