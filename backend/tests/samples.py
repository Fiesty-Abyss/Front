"""测试和演示用的“原创示例文件”生成器：全部由程序现场生成，不含任何第三方素材。

- 灯塔 glTF / GLB / VRM（几何体由圆柱、圆锥拼成，VRM 元数据写明是示例）
- PMX 小模型（一个带贴图的八面体灯笼）
- Live2D 结构示例（model3.json + 只有文件头的 .moc3 + 生成的贴图 / 动作 json，用来演示信息读取，不是可用模型）
- 最小可用的 docx / xlsx / pptx / PDF / WAV
"""

from __future__ import annotations

import io
import json
import math
import struct
import wave
import zipfile
from typing import Any

from PIL import Image, ImageDraw


def png(color=(154, 106, 208), size=(64, 64), label: str | None = None) -> bytes:
    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    for i in range(0, size[0], 8):
        d.line([(i, 0), (0, i)], fill=tuple(min(255, c + 40) for c in color))
    if label:
        d.text((4, 4), label, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ── 几何体 ──
def _cylinder(r0: float, r1: float, y0: float, y1: float, seg: int = 24):
    pos, nrm, idx = [], [], []
    for i in range(seg + 1):
        a = 2 * math.pi * i / seg
        c, s = math.cos(a), math.sin(a)
        slope = (r0 - r1) / max(y1 - y0, 1e-6)
        n = (c, slope, s)
        ln = math.sqrt(sum(x * x for x in n))
        n = tuple(x / ln for x in n)
        pos += [(r0 * c, y0, r0 * s), (r1 * c, y1, r1 * s)]
        nrm += [n, n]
    for i in range(seg):
        a, b, c2, d = 2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 3
        idx += [a, b, c2, b, d, c2]
    return pos, nrm, idx


LIGHTHOUSE = [  # (下半径, 上半径, 底, 顶, 颜色)
    (0.55, 0.42, 0.0, 0.8, (0.93, 0.93, 0.96, 1)),
    (0.42, 0.34, 0.8, 1.6, (0.78, 0.25, 0.32, 1)),
    (0.34, 0.28, 1.6, 2.3, (0.93, 0.93, 0.96, 1)),
    (0.36, 0.36, 2.3, 2.42, (0.2, 0.2, 0.28, 1)),
    (0.22, 0.22, 2.42, 2.75, (1.0, 0.86, 0.45, 1)),
    (0.3, 0.0, 2.75, 3.15, (0.42, 0.3, 0.65, 1)),
]


def gltf_lighthouse(vrm: str | None = None, thumb: bytes | None = None) -> tuple[dict[str, Any], bytes]:
    bin_ = bytearray()
    doc: dict[str, Any] = {"asset": {"version": "2.0", "generator": "Front 示例生成器"}, "scene": 0,
                           "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "【示例】灯塔"}],
                           "meshes": [{"name": "lighthouse", "primitives": []}], "materials": [], "accessors": [],
                           "bufferViews": [], "buffers": [{}]}

    def view(data: bytes, target: int | None = None) -> int:
        while len(bin_) % 4:
            bin_.append(0)
        doc["bufferViews"].append({"buffer": 0, "byteOffset": len(bin_), "byteLength": len(data), **({"target": target} if target else {})})
        bin_.extend(data)
        return len(doc["bufferViews"]) - 1

    for i, (r0, r1, y0, y1, col) in enumerate(LIGHTHOUSE):
        pos, nrm, idx = _cylinder(r0, r1, y0, y1)
        pv = view(b"".join(struct.pack("<3f", *p) for p in pos), 34962)
        nv = view(b"".join(struct.pack("<3f", *n) for n in nrm), 34962)
        iv = view(b"".join(struct.pack("<H", x) for x in idx), 34963)
        xs, ys, zs = zip(*pos)
        doc["accessors"] += [
            {"bufferView": pv, "componentType": 5126, "count": len(pos), "type": "VEC3", "min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]},
            {"bufferView": nv, "componentType": 5126, "count": len(nrm), "type": "VEC3"},
            {"bufferView": iv, "componentType": 5123, "count": len(idx), "type": "SCALAR"},
        ]
        a = len(doc["accessors"])
        doc["materials"].append({"name": f"part{i}", "pbrMetallicRoughness": {"baseColorFactor": list(col), "metallicFactor": 0.05, "roughnessFactor": 0.6},
                                 **({"emissiveFactor": [1.0, 0.8, 0.35]} if i == 4 else {})})
        doc["meshes"][0]["primitives"].append({"attributes": {"POSITION": a - 3, "NORMAL": a - 2}, "indices": a - 1, "material": i})
    if thumb:
        doc["images"] = [{"bufferView": view(thumb), "mimeType": "image/png"}]
        doc["textures"] = [{"source": 0}]
    if vrm == "1.0":
        doc["extensionsUsed"] = ["VRMC_vrm"]
        doc["extensions"] = {"VRMC_vrm": {"specVersion": "1.0", "meta": {
            "name": "【示例】灯塔守望者（VRM 元数据演示）", "version": "1.0", "authors": ["Front 示例生成器"],
            "licenseUrl": "https://vrm.dev/licenses/1.0/", "avatarPermission": "everyone", "commercialUsage": "personalNonProfit",
            "allowRedistribution": False, "modification": "prohibited", "creditNotation": "required",
            **({"thumbnailImage": 0} if thumb else {})}, "humanoid": {"humanBones": {}}}}
    doc["buffers"][0]["byteLength"] = len(bin_)
    return doc, bytes(bin_)


def glb(doc: dict[str, Any], bin_: bytes) -> bytes:
    j = json.dumps(doc, ensure_ascii=False).encode("utf-8")
    j += b" " * (-len(j) % 4)
    b = bin_ + b"\x00" * (-len(bin_) % 4)
    body = struct.pack("<I4s", len(j), b"JSON") + j + struct.pack("<I4s", len(b), b"BIN\x00") + b
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def obj_lighthouse() -> bytes:
    lines = ["# 【示例】灯塔 OBJ（Front 示例生成器）", "mtllib lighthouse.mtl"]
    base = 1
    for i, (r0, r1, y0, y1, _c) in enumerate(LIGHTHOUSE):
        pos, _n, idx = _cylinder(r0, r1, y0, y1, 16)
        lines.append(f"o part{i}")
        lines.append(f"usemtl part{i}")
        lines += [f"v {x:.4f} {y:.4f} {z:.4f}" for x, y, z in pos]
        lines += [f"f {idx[k] + base} {idx[k + 1] + base} {idx[k + 2] + base}" for k in range(0, len(idx), 3)]
        base += len(pos)
    return ("\n".join(lines) + "\n").encode()


# ── PMX ──
def pmx_lantern(texture: str = "tex/lantern.png") -> bytes:
    """八面体“灯笼”：6 个顶点、8 个面、1 个带贴图的材质、1 根骨骼。"""
    def s(t: str) -> bytes:
        b = t.encode("utf-16-le")
        return struct.pack("<i", len(b)) + b

    verts = [(0, 1.6, 0), (0.6, 0.8, 0), (0, 0.8, 0.6), (-0.6, 0.8, 0), (0, 0.8, -0.6), (0, 0, 0)]
    uvs = [(0.5, 0), (0, 0.5), (0.33, 0.5), (0.66, 0.5), (1, 0.5), (0.5, 1)]
    faces = [(0, 2, 1), (0, 3, 2), (0, 4, 3), (0, 1, 4), (5, 1, 2), (5, 2, 3), (5, 3, 4), (5, 4, 1)]
    out = bytearray(b"PMX " + struct.pack("<f", 2.0) + bytes([8, 0, 0, 1, 1, 1, 1, 1, 1]))
    out += s("【示例】灯笼") + s("Sample Lantern") + s("Front 示例生成器制作的演示模型。") + s("Generated sample model.")
    out += struct.pack("<i", len(verts))
    for (x, y, z), (u, v) in zip(verts, uvs):
        ln = math.sqrt(x * x + (y - 0.8) ** 2 + z * z) or 1
        out += struct.pack("<8f", x, y, z, x / ln, (y - 0.8) / ln, z / ln, u, v) + bytes([0]) + struct.pack("<b", 0) + struct.pack("<f", 1.0)
    out += struct.pack("<i", len(faces) * 3) + b"".join(struct.pack("<3b", *f) for f in faces)
    out += struct.pack("<i", 1) + s(texture)
    out += struct.pack("<i", 1) + s("灯笼") + s("lantern")
    out += struct.pack("<4f3ff3f", 1, 1, 1, 1, 0.2, 0.2, 0.2, 5, 0.5, 0.5, 0.5) + bytes([0x01]) + struct.pack("<4ff", 0, 0, 0, 1, 1)
    out += struct.pack("<bb", 0, -1) + bytes([0, 1, 0]) + s("") + struct.pack("<i", len(faces) * 3)
    out += struct.pack("<i", 1) + s("センター") + s("center") + struct.pack("<3f", 0, 0, 0) + struct.pack("<b", -1) + struct.pack("<i", 0) + struct.pack("<H", 0x001E) + struct.pack("<3f", 0, 1, 0)
    out += struct.pack("<i", 0)  # 表情
    out += struct.pack("<i", 1) + s("Root") + s("Root") + bytes([1]) + struct.pack("<i", 0)  # 显示枠
    out += struct.pack("<i", 0) * 2  # 刚体、关节
    return bytes(out)


def pmx_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("灯笼/【示例】灯笼.pmx", pmx_lantern())
        z.writestr("灯笼/tex/lantern.png", png((240, 170, 90), (128, 128), "lantern"))
        z.writestr("灯笼/readme.txt", "Front 示例生成器制作的演示模型。")
    return buf.getvalue()


# ── Live2D 结构示例 ──
def live2d_zip(version: int = 3) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        r = "sample_live2d/"
        z.writestr(r + "sample.model3.json", json.dumps({
            "Version": 3, "FileReferences": {
                "Moc": "sample.moc3", "Textures": ["sample.2048/texture_00.png", "sample.2048/texture_01.png"],
                "Physics": "sample.physics3.json", "DisplayInfo": "sample.cdi3.json",
                "Expressions": [{"Name": "微笑", "File": "exp/smile.exp3.json"}, {"Name": "惊讶", "File": "exp/surprise.exp3.json"}],
                "Motions": {"Idle": [{"File": "motion/idle_01.motion3.json"}, {"File": "motion/idle_02.motion3.json"}],
                            "TapBody": [{"File": "motion/tap.motion3.json"}]}},
            "Groups": [{"Target": "Parameter", "Name": "EyeBlink", "Ids": ["ParamEyeLOpen", "ParamEyeROpen"]},
                       {"Target": "Parameter", "Name": "LipSync", "Ids": ["ParamMouthOpenY"]}],
            "HitAreas": [{"Id": "HitAreaHead", "Name": "头"}, {"Id": "HitAreaBody", "Name": "身体"}]}, ensure_ascii=False))
        z.writestr(r + "sample.moc3", b"MOC3" + bytes([version]) + b"\x00" * 59)
        z.writestr(r + "sample.2048/texture_00.png", png((236, 160, 190), (256, 256), "texture_00"))
        z.writestr(r + "sample.2048/texture_01.png", png((120, 150, 230), (256, 256), "texture_01"))
        z.writestr(r + "sample.physics3.json", "{}")
        z.writestr(r + "sample.cdi3.json", "{}")
        for n in ("smile", "surprise"):
            z.writestr(f"{r}exp/{n}.exp3.json", "{}")
        for n in ("idle_01", "idle_02", "tap"):
            z.writestr(f"{r}motion/{n}.motion3.json", "{}")
    return buf.getvalue()


# ── Office / PDF / 音频 ──
CT = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
CORE = ('<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/">'
        '<dc:title>{title}</dc:title><dc:creator>Front 示例生成器</dc:creator><dcterms:created>2026-10-17T08:00:00Z</dcterms:created></cp:coreProperties>')
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'


def docx(title: str, paras: list[tuple[str, str]]) -> bytes:
    body = "".join(f'<w:p><w:pPr><w:pStyle w:val="{st}"/></w:pPr><w:r><w:t>{t}</w:t></w:r></w:p>' if st else f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for st, t in paras)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("word/document.xml", f"<w:document {W}><w:body>{body}</w:body></w:document>")
        z.writestr("docProps/core.xml", CORE.format(title=title))
        z.writestr("docProps/thumbnail.png", png((60, 70, 110), (120, 160), "docx"))
    return buf.getvalue()


def pptx(title: str, slides: list[list[str]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("docProps/core.xml", CORE.format(title=title))
        for i, lines in enumerate(slides, 1):
            ps = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in lines)
            z.writestr(f"ppt/slides/slide{i}.xml", f"<p:sld {A}><p:cSld><p:spTree><p:sp><p:txBody>{ps}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>")
    return buf.getvalue()


def xlsx(title: str, rows: list[list[str]]) -> bytes:
    strings: list[str] = []
    cells = []
    for r, row in enumerate(rows, 1):
        cs = []
        for c, v in enumerate(row):
            ref = f"{chr(65 + c)}{r}"
            if isinstance(v, (int, float)):
                cs.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                strings.append(v)
                cs.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
        cells.append(f'<row r="{r}">{"".join(cs)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("docProps/core.xml", CORE.format(title=title))
        z.writestr("xl/workbook.xml", f'<workbook {ns}><sheets><sheet name="角色表" sheetId="1"/><sheet name="备注" sheetId="2"/></sheets></workbook>')
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(f"<si><t>{t}</t></si>" for t in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{''.join(cells)}</sheetData></worksheet>")
    return buf.getvalue()


def pdf(title: str, pages: list[str]) -> bytes:
    """手写的最小 PDF（ASCII 文本），带标题与作者。"""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", ""]
    kids = []
    for i, t in enumerate(pages):
        content = f"BT /F1 24 Tf 72 720 Td ({t}) Tj ET".encode()
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {3 + 2 * len(pages)} 0 R >> >> /Contents {4 + 2 * i} 0 R >>")
        objs.append(f"<< /Length {len(content)} >>\nstream\n{content.decode()}\nendstream")
        kids.append(f"{3 + 2 * i} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>"
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objs.append(f"<< /Title ({title}) /Author (Front sample generator) /CreationDate (D:20261017080000) >>")
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for n, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{n} 0 obj\n{o}\nendobj\n".encode()
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{o:010d} 00000 n \n" for o in offs).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info {len(objs)} 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    return bytes(out)


def wav(seconds: float = 1.0, rate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        notes = [523.25, 659.25, 783.99, 659.25]
        frames = bytearray()
        for i in range(int(seconds * rate)):
            f = notes[int(i / rate * 4) % 4]
            frames += struct.pack("<h", int(8000 * math.sin(2 * math.pi * f * i / rate)))
        w.writeframes(bytes(frames))
    return buf.getvalue()
