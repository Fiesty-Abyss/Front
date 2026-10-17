"""写入一套【示例】数据，方便第一次打开时体验各个页面。

python -m front_api.seed            # 写入默认数据目录（FRONT_DATA_DIR）
示例内容全部为原创虚构，图片为程序生成的几何占位图，不含任何第三方作品素材。
"""

from __future__ import annotations

import io
import json
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from .main import create_app

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def _font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def placeholder(label: str, palette: tuple[tuple[int, int, int], tuple[int, int, int]], seed: int,
                size=(640, 800), sd_params: str | None = None, text_chunks: dict[str, str] | None = None,
                badge: str | None = None) -> bytes:
    rnd = random.Random(seed)
    w, h = size
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    (r1, g1, b1), (r2, g2, b2) = palette
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t)))
    for _ in range(14):
        x, y, r = rnd.randint(0, w), rnd.randint(0, h), rnd.randint(20, 160)
        c = tuple(min(255, v + rnd.randint(20, 90)) for v in palette[rnd.randint(0, 1)])
        d.ellipse([x - r, y - r, x + r, y + r], outline=c, width=rnd.randint(2, 6))
    d.rectangle([0, h - 120, w, h], fill=(20, 20, 32))
    d.text((28, h - 104), label, font=_font(40), fill=(255, 255, 255))
    d.text((28, h - 50), "示例占位图 · Front sample", font=_font(22), fill=(200, 200, 220))
    if badge:  # 差分标记：同一张占位图上换一个角标，模拟 CG 差分
        d.rounded_rectangle([w - 190, 24, w - 24, 92], radius=14, fill=(244, 114, 182))
        d.text((w - 172, 34), badge, font=_font(34), fill=(255, 255, 255))
    buf = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    if sd_params:
        info.add_text("parameters", sd_params)
    for k, v in (text_chunks or {}).items():
        info.add_text(k, v)
    img.save(buf, "PNG", pnginfo=info)
    return buf.getvalue()


def _fake_safetensors(meta: dict[str, str], payload_size: int, seed: int) -> bytes:
    """生成一个格式合法、但不含任何真实权重的 safetensors 文件（只用于演示扫描与哈希）。"""
    rnd = random.Random(seed)
    body = rnd.randbytes(payload_size)
    header = json.dumps({"__metadata__": meta, "example.weight": {"dtype": "U8", "shape": [payload_size], "data_offsets": [0, payload_size]}},
                        ensure_ascii=False).encode()
    header += b" " * (-len(header) % 8)
    return len(header).to_bytes(8, "little") + header + body


def make_sample_model_dir(root: Path) -> Path:
    """在 root 下生成一个模仿 SD WebUI 的 models 目录：几个假的示例模型文件 + 预览图 + 说明文件。
    文件名都带 example，内容不是真实模型，只用于演示“扫描模型目录”。返回 models 目录。"""
    models = root / "models"
    note = "Front 示例：假的模型文件，只用于演示扫描，不是真实模型"
    files = {
        "Stable-diffusion/inkline_v2_example.safetensors": ({"modelspec.architecture": "stable-diffusion-xl-v1-base", "modelspec.title": "InkLine v2 (example)", "note": note}, 1_200_000),
        "Lora/linxi_character_example.safetensors": ({"ss_network_module": "networks.lora", "ss_base_model_version": "sdxl_base_v1-0", "ss_output_name": "linxi_character_example", "note": note}, 40_000),
        "Lora/style/inkwash_style_example.safetensors": ({"ss_network_module": "lycoris.kohya", "ss_base_model_version": "sd_v1", "note": note}, 30_000),
        "VAE/sdxl_vae_example.safetensors": ({"note": note}, 20_000),
        "ESRGAN/4x_softedge_example.pth": (None, 12_000),
        "embeddings/badhand_example.pt": (None, 4_000),
    }
    for i, (rel, (meta, size)) in enumerate(files.items()):
        p = models / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(_fake_safetensors(meta, size, 900 + i) if meta is not None else random.Random(900 + i).randbytes(size))
    ink = models / "Stable-diffusion/inkline_v2_example"
    Path(f"{ink}.preview.png").write_bytes(placeholder("InkLine v2 · 预览图", ((30, 30, 40), (210, 210, 200)), 950, size=(384, 512)))
    Path(f"{ink}.civitai.info").write_text(json.dumps({
        "id": None, "modelId": None, "name": "v2.0（示例）", "baseModel": "SDXL 1.0",
        "trainedWords": ["inkline", "lineart"], "description": "【示例】本地 .civitai.info 示例文件，并非真实 Civitai 数据",
        "model": {"name": "【示例】InkLine 线稿模型", "type": "Checkpoint", "nsfw": False}, "images": [],
    }, ensure_ascii=False), "utf-8")
    lin = models / "Lora/linxi_character_example"
    Path(f"{lin}.png").write_bytes(placeholder("林汐 LoRA · 预览", ((52, 66, 120), (190, 120, 160)), 951, size=(384, 512)))
    Path(f"{lin}.json").write_text(json.dumps({
        "description": "【示例】原创角色林汐的角色 LoRA（假文件）", "sd version": "SDXL", "activation text": "linxi, lighthouse keeper uniform",
        "preferred weight": 0.8}, ensure_ascii=False), "utf-8")
    for p in models.rglob("*"):
        if p.suffix in (".safetensors", ".pth", ".pt") and not p.with_suffix(".json").exists():
            p.with_suffix(".json").write_text(json.dumps({"description": "【示例】假的模型文件，只用于演示扫描"}, ensure_ascii=False), "utf-8")
    return models


def seed(client: TestClient) -> dict[str, int]:
    def post(path: str, **payload):
        r = client.post(path, json=payload)
        r.raise_for_status()
        return r.json()["id"]

    def upload(name: str, data: bytes, **form):
        r = client.post("/api/assets/upload", files={"file": (name, data, "image/png")}, data=form)
        r.raise_for_status()
        return r.json()["id"]

    T = {}
    for cat, names in {
        "gender": ["男", "女"],
        "medium": ["动漫", "游戏", "原创", "小说"],
        "source": ["示例·雾港物语", "示例·樱色回廊"],
        "style": ["厚涂", "赛璐璐", "水彩"],
        "type": ["立绘", "场景", "参考", "CG"],
    }.items():
        for n in names:
            T[n] = post("/api/tags", name=n, category=cat)
    # 标签层级与别名：Galgame 归在「游戏」之下，筛选「游戏」时也会包含 Galgame
    T["Galgame"] = post("/api/tags", name="Galgame", category="medium", parent_id=T["游戏"], aliases=["gal", "美少女游戏"], color="#fbbf24")
    T["轻小说"] = post("/api/tags", name="轻小说", category="medium", parent_id=T["小说"], aliases=["ラノベ"])
    T["场景速写"] = post("/api/tags", name="场景速写", category="type", parent_id=T["场景"])
    client.patch(f"/api/tags/{T['女']}", json={"aliases": ["女性"], "color": "#f472b6"}).raise_for_status()
    client.patch(f"/api/tags/{T['男']}", json={"aliases": ["男性"], "color": "#60a5fa"}).raise_for_status()

    work_orig = post("/api/works", title="【示例】雾港物语", kind="original", year=2026,
                     description="原创世界观企划（示例数据）", tag_ids=[T["原创"]])
    work_gal = post("/api/works", title="【示例】樱色回廊", kind="galgame", year=2025, publisher="示例工作室",
                    description="虚构的 galgame 条目，用来演示 CG 归档（示例数据）", tag_ids=[T["Galgame"]])

    world = post(
        "/api/worlds",
        name="【示例】雾港市",
        summary="终年被海雾笼罩的港口城市，灯塔守望者与旧书店维系着城市的记忆。",
        content=(
            "雾港市建在一座半岛上。林汐是灯塔守望者的女儿，与经营旧书店的沈既白是青梅竹马。\n"
            "沈既白的妹妹沈小满在港口学园读书，是林汐的学妹。\n"
            "学园的学生会长陆鸣与林汐是竞争对手，两人在灯塔节的筹办上屡次针锋相对。\n"
            "神秘的旅人艾琳每年雾季到来时出现，向沈既白购买旧地图。"
        ),
        tag_ids=[T["原创"], T["示例·雾港物语"]],
    )

    pal = [((52, 66, 120), (190, 120, 160)), ((30, 90, 110), (220, 200, 140)), ((90, 40, 80), (240, 170, 120)),
           ((40, 40, 60), (120, 170, 220)), ((70, 100, 60), (230, 220, 170)), ((110, 60, 40), (250, 210, 190))]
    chars = {}
    roster = [
        ("林汐", "female", "灯塔守望者的女儿，性格坚韧，擅长读海雾的颜色。", ["女", "原创", "示例·雾港物语"]),
        ("沈既白", "male", "旧书店店主，温和寡言，收藏了大量旧地图。", ["男", "原创", "示例·雾港物语"]),
        ("沈小满", "female", "沈既白的妹妹，港口学园一年级，元气十足。", ["女", "原创", "示例·雾港物语"]),
        ("陆鸣", "male", "港口学园学生会长，完美主义者。", ["男", "原创", "示例·雾港物语"]),
        ("艾琳", "female", "每逢雾季出现的旅人，来历不明。", ["女", "原创", "示例·雾港物语"]),
    ]
    for i, (name, gender, summary, tags) in enumerate(roster):
        avatar = upload(f"avatar_{i}.png", placeholder(f"{name} · 立绘", pal[i], i, size=(480, 640)),
                        title=f"【示例】{name} 立绘", kind="drawing", work_date=f"2026-0{(i % 6) + 4}-1{i}",
                        world_id=str(world), tag_ids=f"{T['立绘']},{T['厚涂' if i % 2 else '赛璐璐']}")
        chars[name] = post("/api/characters", name=name, gender=gender, summary=summary,
                           profile="### 设定\n- 世界观：雾港市\n- 备注：示例条目，可自由编辑或删除。",
                           world_id=world, work_id=work_orig, avatar_asset_id=avatar,
                           tag_ids=[T[t] for t in tags])
    for a, b, kind, desc in [
        ("林汐", "沈既白", "青梅竹马", "从小一起长大"),
        ("沈既白", "沈小满", "兄妹", None),
        ("林汐", "沈小满", "学姐/学妹", None),
        ("林汐", "陆鸣", "竞争对手", "灯塔节筹办上针锋相对"),
        ("艾琳", "沈既白", "顾客", "每年购买旧地图"),
    ]:
        post("/api/relations", source_id=chars[a], target_id=chars[b], kind=kind, description=desc)

    for i, (title, kind, tags, date) in enumerate([
        ("【示例】雾港夜景 · 场景练习", "drawing", ["场景", "水彩"], "2026-09-02"),
        ("【示例】手部结构参考", "material", ["参考"], "2026-08-15"),
        ("【示例】灯塔速写", "drawing", ["场景速写"], "2026-10-01"),
    ]):
        upload(f"misc_{i}.png", placeholder(title.replace("【示例】", ""), pal[(i + 2) % 6], 50 + i),
               title=title, kind=kind, work_date=date, tag_ids=",".join(str(T[t]) for t in tags))
    # galgame CG：先在临时文件夹生成一套带差分命名的占位图，再走“批量导入 · CG 模式”
    cg_dir = Path(tempfile.mkdtemp(prefix="front-sample-cg-")) / "樱色回廊_CG（示例）"
    cg_dir.mkdir()
    cg_specs = [
        ("ev01a", "ev01", "差分 a", 4), ("ev01b", "ev01", "差分 b", 4), ("ev01c", "ev01", "差分 c", 4),
        ("ev02", "ev02", None, 5),
        ("ev03_01", "ev03", "差分 01", 0), ("ev03_02", "ev03", "差分 02", 0),
        ("ev0401", "ev04", "差分 01", 2), ("ev0402", "ev04", "差分 02", 2), ("ev0403", "ev04", "差分 03", 2),
        ("ev05", "ev05", None, 3),
    ]
    for stem, base, badge, p in cg_specs:
        (cg_dir / f"{stem}.png").write_bytes(
            placeholder(f"樱色回廊 {base.upper()}", pal[p], 80 + p, size=(1280, 720), badge=badge))
    r = client.post("/api/import/run", json={"path": str(cg_dir), "cg_mode": True, "work_id": work_gal,
                                             "tag_ids": [T["CG"], T["示例·樱色回廊"]], "use_mtime": False})
    r.raise_for_status()
    cg_ids = r.json()["created_ids"]
    shutil.rmtree(cg_dir.parent, ignore_errors=True)

    novel = """这是一篇用来演示章节拆分与阅读模式的示例小说，人物与地点均为原创虚构。

第一章 雾季
雾从海面升起的时候，林汐正爬上灯塔的第一百零八级台阶。
每年的这个时节，雾港都会被一层乳白色的海雾吞没，街灯在雾里只剩下一圈模糊的光晕。
她把提灯挂在栏杆上，望向港口的方向。那里有一艘晚归的渔船，正循着灯塔的光慢慢靠岸。

第二章 旧书店
沈既白的旧书店开在坡道的尽头，门口的风铃在雾里响得格外清脆。
“又是雾季了。”他把一摞旧地图搬到柜台上，“那位旅人应该快来了。”
沈小满趴在柜台另一侧写作业，头也不抬地问：“哥，她到底要那么多旧地图做什么？”
沈既白没有回答，只是把最上面那张地图的折角轻轻抚平。

第三章 灯塔节
灯塔节的筹备会议上，学生会长陆鸣把一份厚厚的计划书放在桌上。
“今年的灯会路线，我建议改走新港区。”
林汐皱起眉：“灯塔节的灯，从来都是沿着旧港走的。”
两个人的视线在桌面上方撞在一起，会议室里一时安静得能听见窗外的海浪。

尾声
雾散的那天清晨，艾琳在书店门口留下了一张没有署名的明信片。
上面画着雾港的灯塔，灯塔下站着两个小小的人影。
"""
    client.post("/api/assets", json={
        "title": "【示例】雾港短篇 · 灯塔节前夜", "kind": "novel", "work_date": "2026-10-10", "world_id": world,
        "content": novel, "source": "Front 示例数据（原创）",
        "tag_ids": [T["小说"], T["示例·雾港物语"]],
    }).raise_for_status()

    prompt_text = "masterpiece, best quality, 1girl, lighthouse, sea fog, night, lantern light"
    neg = "lowres, bad hands, watermark"
    p1 = post("/api/prompts", title="【示例】雾夜灯塔少女", positive=prompt_text, negative=neg,
              params={"steps": 28, "sampler": "DPM++ 2M Karras", "cfg": 6.5, "size": "640x800", "seed": 20261017},
              notes="示例提示词：用于演示“同一提示词 × 不同模型”的对比", tag_ids=[T["场景"]])
    post("/api/prompts", title="【示例】赛璐璐立绘通用", positive="1girl, full body, standing, white background, flat color",
         negative=neg, params={"steps": 24, "cfg": 7}, tag_ids=[T["立绘"], T["赛璐璐"]])
    models = [
        post("/api/sd-models", name="【示例】AnimeBase XL", kind="checkpoint", base_model="SDXL",
             file_name="animebase_xl_example.safetensors", local_path="D:/sd-webui/models/Stable-diffusion/animebase_xl_example.safetensors",
             notes="示例条目：仅演示登记字段，并无此模型", tag_ids=[T["赛璐璐"]]),
        post("/api/sd-models", name="【示例】PaintFlow 1.5", kind="checkpoint", base_model="SD1.5",
             file_name="paintflow15_example.safetensors", local_path="D:/sd-webui/models/Stable-diffusion/paintflow15_example.safetensors",
             notes="示例条目：仅演示登记字段，并无此模型", tag_ids=[T["厚涂"]]),
        post("/api/sd-models", name="【示例】水彩笔触 LoRA", kind="lora", base_model="SDXL",
             file_name="watercolor_lora_example.safetensors", trigger_words="wtrcolor style",
             local_path="D:/sd-webui/models/Lora/watercolor_lora_example.safetensors",
             notes="示例条目：仅演示登记字段，并无此模型", tag_ids=[T["水彩"]]),
    ]
    model_names = ["AnimeBase XL", "PaintFlow 1.5", "Watercolor LoRA"]
    for i, mid in enumerate(models):
        params = f"{prompt_text}\nNegative prompt: {neg}\nSteps: 28, Sampler: DPM++ 2M Karras, CFG scale: 6.5, Seed: 20261017, Size: 640x800, Model: {model_names[i]} (example)"
        aid = upload(f"gen_{i}.png", placeholder(f"对比 · {model_names[i]}", pal[i * 2 % 6], 100 + i, sd_params=params),
                     title=f"【示例】雾夜灯塔少女 × {model_names[i]}", kind="ai_image", work_date="2026-10-16")
        post("/api/generations", prompt_id=p1, model_id=mid, asset_id=aid, params={"seed": 20261017},
             notes="示例：占位图，并非真实出图")

    r = client.post(f"/api/cards/from-character/{chars['林汐']}")
    r.raise_for_status()
    card_id = r.json()["id"]
    client.patch(f"/api/cards/{card_id}", json={
        "personality": "坚韧、直率，嘴硬心软",
        "scenario": "灯塔节前夜，{{user}} 来到雾港的灯塔下。",
        "first_mes": "（提着灯从台阶上走下来）这么大的雾还出门？{{user}}，你迷路了吧。",
        "mes_example": "<START>\n{{user}}: 灯塔为什么总是亮着？\n{{char}}: 因为总有人在雾里找回家的路。",
        "creator": "Front 示例",
        "character_version": "0.1",
    }).raise_for_status()
    # ComfyUI 出图示例：PNG 内嵌自制的 API 格式 prompt 与界面格式 workflow
    comfy_prompt = {
        "3": {"class_type": "KSampler", "inputs": {"seed": 777, "steps": 30, "cfg": 6.0, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0,
                                                    "model": ["10", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "paintflow15_example.safetensors"}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 640, "height": 800, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt_text, "clip": ["10", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["10", 1]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "front_sample"}},
        "10": {"class_type": "LoraLoader", "inputs": {"lora_name": "watercolor_lora_example.safetensors", "strength_model": 0.7, "strength_clip": 0.7, "model": ["4", 0], "clip": ["4", 1]}},
    }
    comfy_workflow = {"nodes": [{"id": int(k), "type": v["class_type"], "widgets_values": []} for k, v in comfy_prompt.items()], "links": [], "version": 0.4}
    comfy_id = upload("ComfyUI_00042_.png", placeholder("ComfyUI · PaintFlow + 水彩 LoRA", pal[5], 120,
                      text_chunks={"prompt": json.dumps(comfy_prompt), "workflow": json.dumps(comfy_workflow)}),
                      title="【示例】雾夜灯塔少女 · ComfyUI 工作流", work_date="2026-10-17")
    client.post(f"/api/prompts/from-asset/{comfy_id}").raise_for_status()

    assets = client.get("/api/assets", params={"limit": 200}).json()["items"]
    by_title = {a["title"]: a["id"] for a in assets}
    order = ["【示例】雾港夜景 · 场景练习", "【示例】林汐 立绘", "【示例】沈既白 立绘", "【示例】沈小满 立绘",
             "【示例】陆鸣 立绘", "【示例】艾琳 立绘", "【示例】灯塔速写", "【示例】雾港短篇 · 灯塔节前夜"]
    post("/api/collections", name="【示例】雾港物语 · 设定集", description="世界观相关素材，按设定集的页序排列",
         work_id=work_orig, asset_ids=[by_title[t] for t in order], cover_asset_id=by_title["【示例】灯塔速写"], position=0)
    post("/api/collections", name="【示例】樱色回廊 · 精选 CG", description="从 CG 档案里挑出的几张",
         work_id=work_gal, asset_ids=[cg_ids[3], cg_ids[0], cg_ids[9]], position=1)
    post("/api/collections", name="【示例】AI 出图 · 风格对比", description="同一提示词在不同模型下的出图",
         asset_ids=[a["id"] for a in assets if a["kind"] == "ai_image"], position=2)

    # ---------- 第 3 轮：百科 ----------
    def entry(kind: str, name: str, summary: str, parent: int | None = None, content: str = "", chars_: list | None = None, **kw):
        return post("/api/world-entries", world_id=world, kind=kind, name=name, summary=summary, content=content,
                    parent_id=parent, characters=[{"character_id": chars[c], "role": r} for c, r in (chars_ or [])], **kw)

    city = entry("location", "【示例】雾港市", "建在半岛上的港口城市，雾季长达三个月",
                 content="## 城市概况\n- 人口：约 30 万（虚构）\n- 气候：每年 9–11 月为**雾季**\n\n城市分为旧港区与新港区，以运河为界。")
    old = entry("location", "旧港区", "石板路与老仓库，灯塔所在的街区", city)
    lighthouse = entry("location", "灯塔", "旧港区尽头的白色灯塔，共一百零八级台阶", old,
                       content="灯塔由**灯塔守望会**世代看守。雾季时，灯光会按约定的节奏闪烁。", chars_=[("林汐", "居住")])
    shop = entry("location", "坡道书店", "沈既白经营的旧书店，以旧地图收藏闻名", old, chars_=[("沈既白", "店主"), ("沈小满", "常驻")])
    new = entry("location", "新港区", "填海建成的新街区，商业与学校集中于此", city)
    school = entry("location", "港口学园", "雾港市唯一的综合学园", new, chars_=[("林汐", "二年级"), ("沈小满", "一年级"), ("陆鸣", "三年级")])
    entry("organization", "港口学园学生会", "负责筹办每年的灯塔节", school,
                    content="学生会长陆鸣主张改革灯会路线，与守旧派意见相左。",
                    chars_=[("陆鸣", "会长"), ("沈小满", "干事")])
    watch = entry("organization", "灯塔守望会", "世代看守灯塔的民间组织", lighthouse,
                  content="守望会的成员能分辨海雾的颜色，以此判断风暴将至与否。", chars_=[("林汐", "见习守望者")])
    EVENT_NOTES = {"灯塔节筹备会议": (
        "## 经过\n陆鸣带着一份**三十页**的计划书提议：今年灯会改走新港区。\n\n"
        "- 支持：新港区街道宽、游客多\n- 反对：灯塔节的灯从来沿着旧港走\n\n"
        "会议最终没有结论，留到 [[灯塔节前夜]] 再议。")}
    for name, date, key, place, summary, who in [
        ("大雾夜的约定", "灯塔历 296 年 · 冬", 296.9, lighthouse, "童年的林汐与沈既白在灯塔下约定一起守住灯光", [("林汐", "当事人"), ("沈既白", "当事人")]),
        ("旅人初次来访", "灯塔历 299 年 · 雾季", 299.8, shop, "艾琳第一次走进坡道书店，买下全部旧地图", [("艾琳", "旅人"), ("沈既白", "店主")]),
        ("沈小满入学", "灯塔历 302 年 · 春", 302.3, school, "沈小满进入港口学园，成为林汐的学妹", [("沈小满", "新生"), ("林汐", "学姐")]),
        ("灯塔节筹备会议", "灯塔历 302 年 · 秋", 302.8, school, "陆鸣提议改走新港区，与林汐当场争执", [("陆鸣", "提案人"), ("林汐", "反对者"), ("沈小满", "记录")]),
        ("灯塔节前夜", "灯塔历 302 年 · 雾季", 302.9, lighthouse, "大雾中的灯塔节前夜，示例小说的主要舞台", [("林汐", "主角"), ("沈既白", "主角"), ("艾琳", "登场")]),
        ("没有署名的明信片", None, None, shop, "雾散后出现在书店门口的明信片，时间尚未考证", [("艾琳", "疑似寄件人")]),
    ]:
        entry("event", name, summary, place, date_label=date, sort_key=key, chars_=who, content=EVENT_NOTES.get(name, ""))
    entry("item", "旧地图", "坡道书店收藏的雾港旧地图，标注着已消失的航道", shop, chars_=[("沈既白", "收藏者"), ("艾琳", "买家")])
    entry("concept", "海雾的颜色", "守望会用来预判天气的经验：灰雾平安，青雾起风，红雾有暴风", watch)
    entry("concept", "灯塔历", "以灯塔建成之年为元年的本地纪年", city)

    # 角色图集（占位图）与详细设定
    gallery = []
    for j, (label, badge) in enumerate([("林汐 · 表情差分", "表情"), ("林汐 · 便服", "便服"), ("林汐 · 守望者制服", "制服")]):
        gallery.append(upload(f"linxi_{j}.png", placeholder(label, pal[(j + 1) % 6], 200 + j, size=(480, 640), badge=badge),
                              title=f"【示例】{label}", kind="drawing", work_date=f"2026-10-0{j + 3}", world_id=str(world),
                              tag_ids=f"{T['立绘']},{T['赛璐璐']}"))
    lin = client.get(f"/api/characters/{chars['林汐']}").json()
    assets_now = {a["title"]: a["id"] for a in client.get("/api/assets", params={"limit": 200}).json()["items"]}
    client.put(f"/api/characters/{chars['林汐']}/gallery",
               json={"asset_ids": [lin["avatar_asset_id"], *gallery, assets_now["【示例】灯塔速写"]]}).raise_for_status()
    client.patch(f"/api/characters/{chars['林汐']}", json={"alias": "灯塔的女儿", "profile": (
        "## 基本资料\n| 项目 | 内容 |\n|---|---|\n| 年龄 | 17 |\n| 身份 | 港口学园二年级 · 灯塔守望会见习守望者 |\n| 生日 | 灯塔历 285 年 · 雾季 |\n\n"
        "## 性格\n坚韧、直率，**嘴硬心软**。认定的事很少让步，但会在深夜偷偷替别人把灯擦亮。\n\n"
        "## 经历\n1. 童年在 [[灯塔]] 下与 [[沈既白]] 立下约定\n2. 升入港口学园后，在灯塔节路线上与学生会长 [[陆鸣]] 针锋相对\n\n"
        "> 「因为总有人在雾里找回家的路。」\n\n*示例条目：人物与设定均为原创虚构，可自由编辑或删除。*"
    )}).raise_for_status()
    # 出场登记：除来源作品外，再登记一个客串
    post("/api/appearances", character_id=chars["艾琳"], work_id=work_gal, role="客串", note="第 5 章出现的神秘旅人（示例）")
    post("/api/appearances", character_id=chars["林汐"], work_id=work_gal, role="联动角色", note="限定活动（示例）")
    # 一条 AI 待确认的关系 + 关系类型配色
    post("/api/relations", source_id=chars["艾琳"], target_id=chars["林汐"], kind="旧识", description="AI 推测：艾琳似乎认识童年的林汐（示例）",
         ai_suggested=True, confirmed=False)
    client.put("/api/graph/layout", json={"world_id": world, "kind_colors": {
        "青梅竹马": "#f472b6", "兄妹": "#34d399", "竞争对手": "#f87171", "学姐/学妹": "#a78bfa", "顾客": "#fbbf24", "旧识": "#94a3b8"}}).raise_for_status()

    # ---------- 第 4 轮：AI 绘画工作流 ----------
    for i, (cat, title, pos, neg, notes) in enumerate([
        ("quality", "通用高质量", "masterpiece, best quality, highly detailed", "lowres, worst quality, jpeg artifacts", "几乎每张都会用"),
        ("quality", "通用负面", "", "bad hands, extra fingers, watermark, signature, text", "只有反向提示词的片段"),
        ("style", "水彩", "watercolor, soft edges, paper texture", None, "配合水彩 LoRA 更明显"),
        ("style", "厚涂", "impasto, thick paint, painterly", None, None),
        ("style", "赛璐璐", "cel shading, flat color, clean lineart", None, None),
        ("character", "林汐（原创）", "1girl, silver hair, blue eyes, lighthouse keeper uniform", None, "示例角色：原创虚构"),
        ("clothing", "雨衣", "yellow raincoat, rain boots", None, None),
        ("clothing", "学园制服", "school uniform, sailor collar, pleated skirt", None, None),
        ("pose", "提灯回望", "holding lantern, looking back", None, None),
        ("composition", "远景仰视", "wide shot, from below, dramatic angle", None, None),
        ("composition", "半身特写", "upper body, close-up", None, None),
        ("background", "雾夜港口", "harbor, sea fog, night, lighthouse beam", None, None),
        ("lighting", "逆光", "backlighting, rim light, glowing", None, None),
        ("lighting", "黄昏", "sunset, golden hour, warm light", None, None),
    ]):
        post("/api/prompt-snippets", title=f"【示例】{title}", category=cat, positive=pos, negative=neg, notes=notes, position=i)

    # 用内置的“模拟 SD 接口”跑两次出图任务，演示 XY 网格：没有真的调用 SD，图片是占位图
    from . import sdgen
    from .mock_sd import create_mock_app

    mock = create_mock_app()
    saved = (sdgen.client_factory, sdgen.backend_url, sdgen.POLL_INTERVAL)
    sdgen.client_factory = lambda url, timeout: TestClient(mock, base_url=url)
    sdgen.backend_url = lambda backend, override=None: f"http://mock-{backend}"
    sdgen.POLL_INTERVAL = 0.01
    batches = []
    try:
        model_list = client.get("/api/sd-models", params={"limit": 50}).json()["items"]
        ck = {x["name"]: x["id"] for x in model_list}
        for body in (
            {"backend": "webui", "prompt_id": p1, "model_ids": [ck["【示例】AnimeBase XL"], ck["【示例】PaintFlow 1.5"]],
             "y": {"param": "cfg", "values": [5, 7, 9]}, "steps": 28, "sampler": "DPM++ 2M", "seed": 20261017,
             "width": 512, "height": 640, "collection_name": "【示例】XY 网格 · 模型 × CFG", "tag_ids": [T["场景"]]},
            {"backend": "comfyui", "prompt_id": p1, "model_ids": [ck["【示例】PaintFlow 1.5"]],
             "loras": [{"model_id": ck["【示例】水彩笔触 LoRA"], "weight": 0.7}],
             "x": {"param": "prompt_sr", "values": ["night", "dawn", "sunset"]}, "steps": 30, "cfg": 6,
             "sampler": "dpmpp_2m", "scheduler": "karras", "seed": 777, "width": 512, "height": 640},
        ):
            r = client.post("/api/generate", json=body)
            r.raise_for_status()
            job = r.json()
            for _ in range(600):
                j = client.get(f"/api/jobs/{job['id']}").json()
                if j["status"] not in ("queued", "running"):
                    break
                time.sleep(0.05)
            if j["status"] != "done":
                raise RuntimeError(f"示例出图失败：{j}")
            batches.append(job["batch"])
    finally:
        sdgen.client_factory, sdgen.backend_url, sdgen.POLL_INTERVAL = saved
    return {"world_id": world, "card_id": card_id, "prompt_id": p1, "batches": batches}


def main() -> None:
    app = create_app()
    with TestClient(app) as client:
        if client.get("/api/stats").json()["characters"] and "--force" not in sys.argv:
            print("数据库里已有数据，跳过示例数据写入（加 --force 强制写入）")
            return
        print(json.dumps(seed(client), ensure_ascii=False))


if __name__ == "__main__":
    main()
