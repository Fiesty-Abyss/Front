"""模拟的 Bangumi / VNDB / 月幕 Galgame 接口，只用于测试和示例截图（不联网也能把游戏库流程跑通）。
里面的游戏、角色、声优全是虚构的【示例】数据，封面是程序生成的几何海报。

    python -m front_api.mock_galgame --port 7863
    FRONT_BANGUMI_API=http://127.0.0.1:7863/bangumi FRONT_VNDB_API=http://127.0.0.1:7863/vndb \\
    FRONT_YMGAL_API=http://127.0.0.1:7863/ymgal python -m front_api
"""

from __future__ import annotations

import argparse
import io
import random
import re
import unicodedata
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import Response

GAMES: list[dict[str, Any]] = [
    {"key": "sakura", "cn": "【示例】樱色回廊", "jp": "【示例】桜色回廊", "en": "Sakurairo Kairou (sample)",
     "aliases": ["樱回", "SakuKai"], "dev": "示例工作室", "date": "2025-03-14", "nsfw": False,
     "palette": ((236, 120, 160), (60, 40, 110)), "bgm": 900001, "vndb": "v90001", "ymgal": 80001,
     "score": 7.9, "rank": 812, "votes": 1320, "vn_rating": 81.2, "length": 1800,
     "tags": ["校园", "恋爱", "樱花", "群像"], "platforms": ["PC", "Nintendo Switch"],
     "desc_cn": "【示例】春天，旧校舍的回廊里开满了樱花。转学生遥在那里遇见了总在画画的凛——"
                "一段关于约定、绘画与毕业季的青春恋爱故事。（虚构的示例简介）",
     "desc_en": "[Sample] A spring romance about promises, paintings and graduation. (fictional sample text)",
     "chars": [("樱井 遥", "Sakurai Haruka", "main", "示例声优 A", (250, 170, 190)),
               ("白石 凛", "Shiraishi Rin", "main", "示例声优 B", (170, 190, 250)),
               ("早濑 千夏", "Hayase Chinatsu", "side", "示例声优 C", (250, 210, 140))]},
    {"key": "fog", "cn": "【示例】雾港夜想曲", "jp": "【示例】霧港ノクターン", "en": "Fog Harbor Nocturne (sample)",
     "aliases": ["雾港", "Nocturne"], "dev": "雾灯社", "date": "2024-11-08", "nsfw": False,
     "palette": ((60, 90, 140), (20, 24, 40)), "bgm": 900002, "vndb": "v90002", "ymgal": 80002,
     "score": 8.4, "rank": 233, "votes": 4210, "vn_rating": 85.6, "length": 2700,
     "tags": ["悬疑", "港口", "夜晚", "推理"], "platforms": ["PC", "PS4"],
     "desc_cn": "【示例】雾季来临的港口城市，灯塔每晚都会熄灭一次。见习守灯人苏晚决定查清真相。（虚构的示例简介）",
     "desc_en": "[Sample] Every night in the fog season, the lighthouse goes dark for one minute. (fictional)",
     "chars": [("苏晚", "Su Wan", "main", "示例声优 D", (140, 200, 230)),
               ("陆沉", "Lu Chen", "main", "示例声优 E", (200, 200, 220)),
               ("守望会会长", None, "side", None, (120, 130, 160))]},
    {"key": "star", "cn": "【示例】星屑邮局", "jp": "【示例】星屑郵便局", "en": "Stardust Post Office (sample)",
     "aliases": ["星邮"], "dev": "纸灯社", "date": "2023-07-21", "nsfw": False,
     "palette": ((110, 90, 200), (16, 18, 48)), "bgm": 900003, "vndb": "v90003", "ymgal": None,
     "score": 7.2, "rank": 1630, "votes": 860, "vn_rating": 74.0, "length": 900,
     "tags": ["奇幻", "治愈", "短篇"], "platforms": ["PC"],
     "desc_cn": "【示例】只在流星夜营业的邮局，替人把信寄给过去的自己。（虚构的示例简介）",
     "desc_en": "[Sample] A post office that opens only on meteor nights. (fictional)",
     "chars": [("星野 雫", "Hoshino Shizuku", "main", "示例声优 F", (190, 170, 250))]},
    {"key": "summer", "cn": "【示例】夏日方程式", "jp": "【示例】なつのほうていしき", "en": "Summer Equation (sample)",
     "aliases": ["夏程"], "dev": "示例工作室", "date": "2026-08-01", "nsfw": False,
     "palette": ((80, 200, 210), (240, 200, 120)), "bgm": None, "vndb": "v90004", "ymgal": 80004,
     "score": None, "rank": None, "votes": 120, "vn_rating": 70.4, "length": 1200,
     "tags": ["夏天", "数学", "海边"], "platforms": ["PC", "Android"],
     "desc_cn": "【示例】数学社最后一个暑假，要在海边小镇解开一道没人解开的方程。（虚构的示例简介）",
     "desc_en": "[Sample] The math club's last summer by the sea. (fictional)",
     "chars": [("七海 葵", "Nanami Aoi", "main", "示例声优 G", (120, 220, 220))]},
    {"key": "night", "cn": "【示例】白夜图书馆", "jp": "【示例】白夜図書館", "en": "White Night Library (sample)",
     "aliases": ["白夜"], "dev": "雾灯社", "date": "2022-12-02", "nsfw": True,
     "palette": ((200, 70, 90), (30, 10, 30)), "bgm": 900005, "vndb": "v90005", "ymgal": 80005,
     "score": 6.8, "rank": 2900, "votes": 540, "vn_rating": 68.0, "length": 1500,
     "tags": ["哥特", "图书馆", "成人向（示例标记）"], "platforms": ["PC"],
     "desc_cn": "【示例】标记为限制级的示例条目，用来演示 NSFW 封面模糊。（虚构的示例简介）",
     "desc_en": "[Sample] Marked as adult-only to demonstrate cover blurring. (fictional)",
     "chars": [("夜宫 澄", "Yamiya Sumi", "main", "示例声优 H", (220, 120, 140))]},
    {"key": "bell", "cn": "【示例】月下钟楼", "jp": "【示例】月下の鐘楼", "en": "Bell Tower under the Moon (sample)",
     "aliases": ["钟楼", "Moonbell"], "dev": "纸灯社", "date": "2026-02-14", "nsfw": False,
     "palette": ((230, 190, 120), (40, 30, 70)), "bgm": 900006, "vndb": "v90006", "ymgal": 80006,
     "score": 7.6, "rank": 1104, "votes": 980, "vn_rating": 77.3, "length": 1300,
     "tags": ["奇幻", "钟楼", "月夜"], "platforms": ["PC", "Nintendo Switch"],
     "desc_cn": "【示例】每到满月，钟楼会多敲一下——那一声只有修钟的少女听得见。（虚构的示例简介）",
     "desc_en": "[Sample] On full moon nights the bell tower rings one extra time. (fictional)",
     "chars": [("月见 铃", "Tsukimi Suzu", "main", "示例声优 I", (240, 210, 150)),
               ("钟守", None, "side", "示例声优 J", (160, 150, 200))]},
    {"key": "tide", "cn": "【示例】海潮信号", "jp": "【示例】潮騒シグナル", "en": "Tide Signal (sample)",
     "aliases": ["潮信"], "dev": "示例工作室", "date": "2021-09-10", "nsfw": False,
     "palette": ((70, 170, 200), (20, 40, 70)), "bgm": 900007, "vndb": "v90007", "ymgal": 80007,
     "score": 7.0, "rank": 3100, "votes": 410, "vn_rating": 71.5, "length": 700,
     "tags": ["海边", "无线电", "短篇"], "platforms": ["PC"],
     "desc_cn": "【示例】废弃灯塔里的旧电台，每晚都会收到来自十年前的信号。（虚构的示例简介）",
     "desc_en": "[Sample] An old radio in an abandoned lighthouse receives signals from ten years ago. (fictional)",
     "chars": [("潮見 汐里", "Shiomi Shiori", "main", "示例声优 K", (130, 200, 220))]},
]


def _norm(s: str | None) -> str:
    return re.sub(r"[\s\W_]+", "", unicodedata.normalize("NFKC", s or "").lower()).replace("示例", "")


def _hits(q: str) -> list[dict[str, Any]]:
    n = _norm(q)
    if not n:
        return []
    out = []
    for g in GAMES:
        names = [g["cn"], g["jp"], g["en"], *g["aliases"]]
        if any(n in _norm(x) or (len(_norm(x)) >= 2 and _norm(x) in n) for x in names):
            out.append(g)
    return out


def poster(title: str, sub: str, palette: tuple[tuple[int, int, int], tuple[int, int, int]], seed: int,
           size: tuple[int, int] = (600, 860)) -> bytes:
    from PIL import Image, ImageDraw, ImageFilter

    from .seed import _font

    rnd = random.Random(seed)
    w, h = size
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    (r1, g1, b1), (r2, g2, b2) = palette
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t)))
    glow = Image.new("RGB", size, (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for _ in range(9):
        x, y, r = rnd.randint(0, w), rnd.randint(0, int(h * 0.7)), rnd.randint(40, 190)
        gd.ellipse([x - r, y - r, x + r, y + r], fill=tuple(min(255, v + 70) for v in palette[0]))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(40)), 0.35)
    d = ImageDraw.Draw(img)
    for _ in range(60):  # 星点 / 花瓣
        x, y, r = rnd.randint(0, w), rnd.randint(0, h), rnd.choice([1, 1, 2, 3])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
    cx = w // 2
    d.ellipse([cx - 150, 190, cx + 150, 490], outline=(255, 255, 255), width=3)
    d.ellipse([cx - 120, 220, cx + 120, 460], outline=(255, 255, 255, 120), width=1)
    d.rectangle([0, h - 250, w, h], fill=(14, 14, 24))
    d.text((36, h - 225), title.replace("【示例】", ""), font=_font(52), fill=(255, 255, 255))
    d.text((38, h - 150), sub, font=_font(24), fill=(210, 210, 230))
    d.text((38, h - 70), "【示例】程序生成的封面 · Front sample", font=_font(20), fill=(160, 160, 190))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def avatar(name: str, color: tuple[int, int, int], seed: int) -> bytes:
    from PIL import Image, ImageDraw

    from .seed import _font

    img = Image.new("RGB", (240, 320), tuple(max(0, v - 90) for v in color))
    d = ImageDraw.Draw(img)
    d.ellipse([60, 50, 180, 170], fill=color)
    d.rounded_rectangle([40, 180, 200, 330], radius=60, fill=color)
    d.text((16, 280), name[:6], font=_font(26), fill=(20, 20, 30))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def create_mock_app() -> FastAPI:
    app = FastAPI(title="Front mock galgame metadata")

    def root(request: Request) -> str:
        return str(request.base_url).rstrip("/")

    def cover(request: Request, g: dict[str, Any]) -> str:
        return f"{root(request)}/img/cover/{g['key']}.png"

    def ch_img(request: Request, g: dict[str, Any], i: int) -> str:
        return f"{root(request)}/img/char/{g['key']}-{i}.png"

    @app.get("/img/cover/{key}.png")
    def img_cover(key: str) -> Response:
        g = next((x for x in GAMES if x["key"] == key), None)
        if not g:
            raise HTTPException(404)
        return Response(poster(g["cn"], f"{g['jp'].replace('【示例】', '')} · {g['dev']}", g["palette"],
                               sum(map(ord, key))), media_type="image/png")

    @app.get("/img/char/{key}-{i}.png")
    def img_char(key: str, i: int) -> Response:
        g = next((x for x in GAMES if x["key"] == key), None)
        if not g or i >= len(g["chars"]):
            raise HTTPException(404)
        c = g["chars"][i]
        return Response(avatar(c[0], c[4], i), media_type="image/png")

    # ---- Bangumi
    def bgm_subject(request: Request, g: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": g["bgm"], "type": 4, "name": g["jp"], "name_cn": g["cn"], "date": g["date"], "platform": "游戏",
            "summary": g["desc_cn"], "nsfw": g["nsfw"],
            "images": {"large": cover(request, g), "common": cover(request, g)},
            "rating": {"score": g["score"], "rank": g["rank"], "total": g["votes"]},
            "tags": [{"name": t, "count": 100 - i} for i, t in enumerate(g["tags"])],
            "infobox": [{"key": "中文名", "value": g["cn"]}, {"key": "别名", "value": [{"v": a} for a in g["aliases"]]},
                        {"key": "平台", "value": [{"v": p} for p in g["platforms"]]}, {"key": "开发", "value": g["dev"]},
                        {"key": "官方网站", "value": f"https://example.com/{g['key']}"}],
        }

    @app.post("/bangumi/v0/search/subjects")
    def bgm_search(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        rows = [bgm_subject(request, g) for g in _hits(body.get("keyword", "")) if g["bgm"]]
        return {"data": rows, "total": len(rows), "limit": 10, "offset": 0}

    @app.get("/bangumi/v0/subjects/{sid}")
    def bgm_get(request: Request, sid: int) -> dict[str, Any]:
        g = next((x for x in GAMES if x["bgm"] == sid), None)
        if not g:
            raise HTTPException(404)
        return bgm_subject(request, g)

    @app.get("/bangumi/v0/subjects/{sid}/characters")
    def bgm_chars(request: Request, sid: int) -> list[dict[str, Any]]:
        g = next((x for x in GAMES if x["bgm"] == sid), None)
        if not g:
            raise HTTPException(404)
        return [{"id": 700000 + sid % 1000 * 10 + i, "name": c[0], "relation": "主角" if c[2] == "main" else "配角",
                 "images": {"medium": ch_img(request, g, i)}, "actors": [{"name": c[3]}] if c[3] else []}
                for i, c in enumerate(g["chars"])]

    # ---- VNDB
    def vn(request: Request, g: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": g["vndb"], "title": g["en"], "alttitle": g["jp"],
            "titles": [{"title": g["jp"], "lang": "ja", "main": True}, {"title": g["cn"], "lang": "zh-Hans", "main": False},
                       {"title": g["en"], "lang": "en", "main": False}],
            "aliases": g["aliases"], "released": g["date"], "developers": [{"name": g["dev"]}],
            "image": {"url": cover(request, g), "sexual": 2 if g["nsfw"] else 0}, "description": g["desc_en"],
            "rating": g["vn_rating"], "votecount": g["votes"], "length_minutes": g["length"],
            "platforms": ["win"], "languages": ["ja", "zh-Hans"],
            "tags": [{"name": t, "rating": 2.5, "spoiler": 0} for t in g["tags"]],
            "extlinks": [{"url": f"https://example.com/{g['key']}", "label": "Official website"}],
            "va": [{"character": {"id": f"c9{g['vndb'][1:]}{i}"}, "staff": {"name": c[3]}}
                   for i, c in enumerate(g["chars"]) if c[3]],
        }

    @app.post("/vndb/vn")
    def vndb_vn(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        f = body.get("filters") or []
        if f[:2] == ["search", "="]:
            rows = [g for g in _hits(f[2]) if g["vndb"]]
        elif f[:2] == ["id", "="]:
            rows = [g for g in GAMES if g["vndb"] == f[2]]
        else:
            rows = []
        return {"results": [vn(request, g) for g in rows], "more": False}

    @app.post("/vndb/character")
    def vndb_char(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        f = body.get("filters") or []
        vid = f[2][2] if len(f) == 3 and isinstance(f[2], list) else None
        g = next((x for x in GAMES if x["vndb"] == vid), None)
        if not g:
            return {"results": []}
        return {"results": [{"id": f"c9{vid[1:]}{i}", "name": c[1] or c[0], "original": c[0],
                             "description": f"【示例】{c[0]}的虚构角色简介。", "image": {"url": ch_img(request, g, i), "sexual": 0},
                             "vns": [{"id": vid, "role": "primary" if c[2] == "main" else "side"}]}
                            for i, c in enumerate(g["chars"])]}

    # ---- 月幕
    @app.get("/ymgal/oauth/token")
    def ym_token(client_id: str = "", client_secret: str = "") -> dict[str, Any]:
        if not client_id or not client_secret:
            raise HTTPException(401)
        return {"access_token": "mock-token", "token_type": "bearer", "expires_in": 3599, "scope": "public"}

    def ym_auth(request: Request) -> None:
        if request.headers.get("authorization") != "Bearer mock-token" or request.headers.get("version") != "1":
            raise HTTPException(401)

    @app.get("/ymgal/open/archive/search-game")
    def ym_search(request: Request, keyword: str = "", mode: str = "list") -> dict[str, Any]:
        ym_auth(request)
        rows = [{"id": g["ymgal"], "name": g["jp"], "chineseName": g["cn"], "releaseDate": g["date"],
                 "mainImg": cover(request, g), "orgName": g["dev"], "haveChinese": True, "restricted": g["nsfw"]}
                for g in _hits(keyword) if g["ymgal"]]
        return {"success": True, "code": 0, "data": {"result": rows, "total": len(rows), "hasNext": False,
                                                     "pageNum": 1, "pageSize": 10}}

    @app.get("/ymgal/open/archive")
    def ym_archive(request: Request, gid: int | None = None, orgId: int | None = None) -> dict[str, Any]:  # noqa: N803
        ym_auth(request)
        if orgId is not None:
            g = next((x for x in GAMES if x["ymgal"] and x["ymgal"] + 5000 == orgId), None)
            if not g:
                return {"success": False, "code": 614, "msg": "找不到"}
            return {"success": True, "code": 0, "data": {"org": {"orgId": orgId, "name": g["dev"], "chineseName": g["dev"]}}}
        g = next((x for x in GAMES if x["ymgal"] == gid), None)
        if not g:
            return {"success": False, "code": 614, "msg": "根据关键字找不到对应档案"}
        game = {
            "gid": g["ymgal"], "name": g["jp"], "chineseName": g["cn"], "developerId": g["ymgal"] + 5000,
            "extensionName": [{"name": a, "type": "", "desc": ""} for a in g["aliases"]], "introduction": g["desc_cn"],
            "mainImg": cover(request, g), "releaseDate": g["date"], "restricted": g["nsfw"], "haveChinese": True,
            "typeDesc": "恋爱ADV", "website": [{"title": "官方网站", "link": f"https://example.com/{g['key']}"}],
            "releases": [{"id": 1, "releaseName": g["cn"], "platform": p} for p in g["platforms"]],
            "characters": [{"cid": 60000 + i, "cvId": 50000 + i if c[3] else None, "characterPosition": 1 if c[2] == "main" else 2}
                           for i, c in enumerate(g["chars"])],
        }
        return {"success": True, "code": 0, "data": {
            "game": game,
            "cidMapping": {str(60000 + i): {"cid": 60000 + i, "name": c[0], "mainImg": ch_img(request, g, i)}
                           for i, c in enumerate(g["chars"])},
            "pidMapping": {str(50000 + i): {"pid": 50000 + i, "name": c[3]} for i, c in enumerate(g["chars"]) if c[3]}}}

    return app


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7863)
    args = ap.parse_args()
    uvicorn.run(create_mock_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
