"""模拟的 OpenAI 兼容 AI 服务，只用于测试、示例数据和截图——它不是真正的语言模型。

实现了 Front 用到的几个接口：
- GET  /v1/models
- POST /v1/chat/completions（支持 stream）：角色扮演回复是模板拼出来的，开头带【模拟回复】；
  抽取角色用简单的规则（姓氏 + 名字）在原文里找人名；看图打标签只根据颜色和长宽比
- POST /v1/embeddings：与 Front 内置的本地 n-gram 向量相同

命令行：python -m front_api.mock_ai --port 7862，然后在设置页添加服务
  地址 http://127.0.0.1:7862/v1，对话模型 mock-chat，嵌入模型 mock-embed，视觉模型 mock-vision。
"""

from __future__ import annotations

import base64
import io
import itertools
import json
import re
import time
from collections import Counter
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .ai.embed import local_embed
from .ai.extract import TASK_MARK as EXTRACT_MARK
from .ai.tagger import TASK_MARK as TAG_MARK

SURNAMES = "林沈陆艾李王张刘陈杨赵黄周吴徐孙朱马胡郭何高罗郑梁谢宋唐许韩冯邓曹彭曾萧田董袁潘蒋蔡杜叶程苏魏吕丁任姚卢姜崔钟谭汪金廖贾夏韦邹孟熊秦邱尹薛闫雷侯龙史陶黎贺顾毛郝龚邵钱严武戴莫孔汤"
NAME_RX = re.compile(rf"(?<![那这一几每整])([{SURNAMES}][\u4e00-\u9fff]{{1,2}}?)(?=正|把|没|皱|的|在|说|问|站|留|趴|头|：|，|。|笑|看|望|轻|低|抬|走|爬|从|接|推|骑|取)")
STOP = {"林中", "陆地", "高处", "周围", "黄昏", "金色", "钟声", "雷声", "龙头"}
_counter = itertools.count()

OPENERS = ["（{act}）", "（{act}，停顿了一下）", "（{act}，声音很轻）"]
ACTS = ["把提灯换到另一只手", "抬头看了看雾里的灯塔", "拢了拢被海风吹乱的头发", "低头整理袖口", "朝港口的方向望了一眼"]
BODIES = [
    "“{echo}？”{char}重复了一遍，“这种事，在雾港可不常听到。”",
    "“你问{echo}……嗯，我知道一点，但得先说好，听完别笑我。”",
    "“{echo}吗。好吧，跟我来，路上慢慢说。”",
]


def _echo(text: str) -> str:
    text = re.sub(r"\s+", "", text or "")
    text = re.sub(r"^[（(].*?[）)]", "", text)
    text = text.rstrip("？?。！!…，,")
    return (text[:14] + "…") if len(text) > 15 else (text or "这个")


def roleplay_reply(messages: list[dict[str, Any]]) -> str:
    system = "\n".join(str(m.get("content")) for m in messages if m.get("role") == "system")
    user = next((str(m.get("content")) for m in reversed(messages) if m.get("role") == "user"), "")
    char = (re.search(r"扮演\s*([^\s。，,]+)", system) or re.search(r"【角色设定】\n([^\s：:，。]{1,8})", system))
    char_name = char.group(1) if char else "我"
    n = next(_counter)
    parts = ["【模拟回复】" + OPENERS[n % len(OPENERS)].format(act=ACTS[(n + len(user)) % len(ACTS)])]
    parts.append(BODIES[(n + len(user)) % len(BODIES)].format(echo=_echo(user), char=char_name))
    lore = re.search(r"【世界书】\n(.+?)(?:\n\n【|$)", system, re.S)
    if lore:
        paras = [p.strip() for p in lore.group(1).split("\n\n") if p.strip()]
        pick = paras[-1] if len(paras) > 1 else paras[0]  # 常驻条目排在最前，取最后命中的那条更贴近话题
        first = re.split(r"[。！？\n]", pick)[0]
        parts.append(f"（想起了世界书里的设定：{first[:32]}。）")
    return "".join(parts)


def extract_reply(messages: list[dict[str, Any]]) -> str:
    text = str(messages[-1].get("content", ""))
    text = text.split("小说片段：", 1)[-1]
    sentences = [x for x in re.split(r"(?<=[。！？”\n])", text) if x.strip()]
    scenes = [x for x in re.split(r"\n(?=第.{1,4}章|尾声|序章)", text) if x.strip()]
    counts: Counter = Counter()
    first: dict[str, str] = {}
    for sent in sentences:
        for name in NAME_RX.findall(sent):
            if name in STOP:
                continue
            counts[name] += 1
            first.setdefault(name, sent.strip()[:60])
    chars = []
    names = list(counts)
    for name in names:
        idx = text.find(name) + len(name)
        nxt = min([p for p in (text.find(o, idx) for o in names if o != name) if p >= 0] or [len(text)])
        pron = re.search(r"[他她]", text[idx:nxt])
        gender = {"她": "女", "他": "男"}.get(pron.group(0) if pron else "", "未知")
        rels = []
        for other in names:
            scene = next((sc for sc in scenes if name in sc and other in sc), None)
            if other != name and scene:
                evidence = next((x for x in re.split(r"(?<=[。！？”])", scene) if other in x), scene).strip()[:60]
                rels.append({"target": other, "kind": "同场出现（模拟推断）", "evidence": evidence})
        chars.append({"name": name, "aliases": [], "gender": gender, "summary": f"原文：{first[name]}",
                      "traits": ["模拟抽取"], "appearance": "", "relations": rels[:3]})
    return json.dumps({"characters": chars}, ensure_ascii=False)


def tag_reply(messages: list[dict[str, Any]]) -> str:
    from PIL import Image

    content = messages[-1].get("content")
    prompt = next((p["text"] for p in content if p.get("type") == "text"), "") if isinstance(content, list) else ""
    url = next((p["image_url"]["url"] for p in content if p.get("type") == "image_url"), "") if isinstance(content, list) else ""
    has_candidates = "候选标签：" in prompt  # 真实模型会参考候选标签；模拟服务固定返回英文标签，靠别名对上
    tags = [{"name": "placeholder (mock)", "score": 0.99 if has_candidates else 0.9}]
    try:
        raw = base64.b64decode(url.split(",", 1)[1])
        with Image.open(io.BytesIO(raw)) as im:
            w, h = im.size
            r, g, b = im.convert("RGB").resize((1, 1)).getpixel((0, 0))
    except Exception:  # noqa: BLE001
        return json.dumps({"tags": tags})
    if h > w * 1.1:
        tags.append({"name": "portrait", "score": 0.72})
    elif w > h * 1.1:
        tags.append({"name": "scenery", "score": 0.81})
    tags.append({"name": "warm colors" if r > b else "blue theme", "score": 0.66})
    if max(r, g, b) < 90:
        tags.append({"name": "night", "score": 0.58})
    return json.dumps({"tags": tags}, ensure_ascii=False)


def answer(messages: list[dict[str, Any]]) -> str:
    system = "\n".join(str(m.get("content")) for m in messages if m.get("role") == "system")
    first = messages[0].get("content") if messages else ""
    if EXTRACT_MARK in system:
        return extract_reply(messages)
    if isinstance(first, list) or TAG_MARK in str(first):
        return tag_reply(messages)
    if "世界观设定分析助手" in system:
        return "[]"
    if len(messages) == 1 and "连接成功" in str(first):
        return "连接成功（模拟服务）"
    return roleplay_reply(messages)


def create_mock_app(delay: float = 0.03) -> FastAPI:
    app = FastAPI(title="Front 模拟 AI 服务（不是真正的模型）")

    @app.get("/v1/models")
    def models() -> dict[str, Any]:
        return {"object": "list", "data": [{"id": x, "object": "model"} for x in ("mock-chat", "mock-embed", "mock-vision")]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> Any:
        body = await request.json()
        text = answer(body.get("messages") or [])
        model = body.get("model", "mock-chat")
        if not body.get("stream"):
            return {"id": "mock", "object": "chat.completion", "model": model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]}

        def gen():
            for i in range(0, len(text), 3):
                chunk = {"id": "mock", "object": "chat.completion.chunk", "model": model,
                         "choices": [{"index": 0, "delta": {"content": text[i:i + 3]}}]}
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                if delay:
                    time.sleep(delay)
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/v1/embeddings")
    async def embeddings(request: Request) -> Any:
        body = await request.json()
        inputs = body.get("input")
        if isinstance(inputs, str):
            inputs = [inputs]
        if not isinstance(inputs, list):
            return JSONResponse({"error": "input 必须是字符串或数组"}, status_code=400)
        vecs = local_embed([str(x) for x in inputs], dim=256)
        return {"object": "list", "model": body.get("model"), "data": [{"index": i, "embedding": v} for i, v in enumerate(vecs)]}

    return app


def main() -> None:
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description="Front 模拟 AI 服务（OpenAI 兼容，仅用于演示）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7862)
    ap.add_argument("--delay", type=float, default=0.03, help="流式输出每段之间的间隔（秒）")
    args = ap.parse_args()
    uvicorn.run(create_mock_app(delay=args.delay), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
