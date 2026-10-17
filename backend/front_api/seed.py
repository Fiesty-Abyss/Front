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

    work_orig = post("/api/works", title="【示例】雾港物语", kind="original", year=2026,
                     description="原创世界观企划（示例数据）", tag_ids=[T["原创"]])
    work_gal = post("/api/works", title="【示例】樱色回廊", kind="galgame", year=2025, publisher="示例工作室",
                    description="虚构的 galgame 条目，用来演示 CG 归档（示例数据）", tag_ids=[T["游戏"]])

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
        ("【示例】灯塔速写", "drawing", ["场景"], "2026-10-01"),
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
    return {"world_id": world, "card_id": card_id, "prompt_id": p1}


def main() -> None:
    app = create_app()
    with TestClient(app) as client:
        if client.get("/api/stats").json()["characters"] and "--force" not in sys.argv:
            print("数据库里已有数据，跳过示例数据写入（加 --force 强制写入）")
            return
        print(json.dumps(seed(client), ensure_ascii=False))


if __name__ == "__main__":
    main()
