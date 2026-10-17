"""图表画布的内置模板（同时用作【示例】数据）。全部是原创内容。"""

from __future__ import annotations

import copy
from typing import Any

PURPLE, CYAN, AMBER, CORAL, MINT, SKY, SLATE = "#9a6ad0", "#23d2e2", "#f2c26b", "#f9515c", "#4fd1a5", "#5b9cf0", "#8a8ca3"


def _n(id: str, x: float, y: float, label: str, shape: str = "rect", color: str = PURPLE, w: int = 168, h: int = 64, **data: Any) -> dict[str, Any]:
    return {"id": id, "type": "shape", "position": {"x": x, "y": y}, "style": {"width": w, "height": h},
            "data": {"label": label, "shape": shape, "color": color, **data}}


def _e(s: str, t: str, label: str | None = None, sh: str = "b", th: str = "t", **extra: Any) -> dict[str, Any]:
    e = {"id": f"e-{s}-{t}", "source": s, "target": t, "sourceHandle": sh, "targetHandle": th, "type": "smoothstep"}
    if label:
        e["label"] = label
    return {**e, **extra}


def _wf(id: str, x: float, y: float, label: str, color: str, inputs: list[str], outputs: list[str], fields: list[tuple[str, Any]]) -> dict[str, Any]:
    return {"id": id, "type": "workflow", "position": {"x": x, "y": y},
            "data": {"label": label, "color": color,
                     "inputs": [{"id": f"i{i}", "label": v} for i, v in enumerate(inputs)],
                     "outputs": [{"id": f"o{i}", "label": v} for i, v in enumerate(outputs)],
                     "fields": [{"label": k, "value": v} for k, v in fields]}}


def _wire(s: str, so: int, t: str, ti: int, color: str = SLATE) -> dict[str, Any]:
    return {"id": f"w-{s}{so}-{t}{ti}", "source": s, "target": t, "sourceHandle": f"out-o{so}", "targetHandle": f"in-i{ti}",
            "type": "default", "style": {"stroke": color}, "data": {"color": color}}


FLOW = {
    "nodes": [
        {"id": "frame", "type": "group", "position": {"x": -40, "y": -60}, "style": {"width": 760, "height": 700}, "zIndex": -1,
         "data": {"label": "第一卷 · 灯塔节", "color": SLATE}},
        _n("start", 230, 0, "雾季来临", "pill", MINT),
        _n("climb", 230, 110, "林汐登上灯塔", "rect", PURPLE, link=None),
        _n("check", 220, 220, "旧灯芯还在吗？", "diamond", AMBER, 188, 104),
        _n("light", 230, 380, "点亮灯塔", "rect", PURPLE),
        _n("shop", 500, 236, "去旧书店找沈既白", "rect", SKY, 176, 72),
        _n("book", 500, 380, "《灯塔与雾》\n里的线索", "document", SKY, 176, 84),
        _n("end", 230, 520, "全城点亮纸灯", "pill", CORAL),
        {"id": "memo", "type": "note", "position": {"x": -10, "y": 360}, "style": {"width": 190, "height": 120},
         "data": {"label": "伏笔：灯芯其实被守望会收走了，第二卷揭晓。", "color": AMBER}},
    ],
    "edges": [
        _e("start", "climb"), _e("climb", "check"), _e("check", "light", "在"),
        _e("check", "shop", "不在", "r", "l"), _e("shop", "book"), _e("book", "light", "找到了", "l", "r"),
        _e("light", "end", animated=True),
    ],
}

WORKFLOW = {
    "nodes": [
        _wf("ckpt", 0, 40, "模型加载", PURPLE, [], ["模型", "CLIP", "VAE"], [("模型", "【示例】AnimeBase XL")]),
        _wf("pos", 300, -40, "正向提示词", MINT, ["CLIP"], ["条件"], [("文本", "1girl, lighthouse, fog, night")]),
        _wf("neg", 300, 150, "反向提示词", CORAL, ["CLIP"], ["条件"], [("文本", "lowres, blurry")]),
        _wf("latent", 300, 330, "空白画布", SLATE, [], ["Latent"], [("尺寸", "832 × 1216")]),
        _wf("sampler", 620, 80, "采样器", SKY, ["模型", "正向", "反向", "Latent"], ["Latent"], [("步数", 28), ("CFG", 6.5), ("采样器", "DPM++ 2M")]),
        _wf("decode", 930, 140, "VAE 解码", AMBER, ["Latent", "VAE"], ["图像"], []),
        _wf("save", 1200, 150, "存入 Front 素材库", PURPLE, ["图像"], [], [("标签", "AI 生成 · 示例")]),
    ],
    "edges": [
        _wire("ckpt", 0, "sampler", 0, PURPLE), _wire("ckpt", 1, "pos", 0, MINT), _wire("ckpt", 1, "neg", 0, CORAL),
        _wire("ckpt", 2, "decode", 1, AMBER), _wire("pos", 0, "sampler", 1, MINT), _wire("neg", 0, "sampler", 2, CORAL),
        _wire("latent", 0, "sampler", 3), _wire("sampler", 0, "decode", 0, SKY), _wire("decode", 0, "save", 0, AMBER),
    ],
}

_branches = [("地点", SKY, ["旧港区", "白色灯塔", "旧书店"]), ("人物", PURPLE, ["林汐", "沈既白", "守望者"]),
             ("组织", MINT, ["灯塔守望会"]), ("事件", AMBER, ["灯塔节", "雾季"])]
MIND: dict[str, Any] = {"nodes": [_n("root", 0, 0, "雾港", "pill", PURPLE, 150, 60)], "edges": []}
for bi, (name, color, leaves) in enumerate(_branches):
    side = 1 if bi % 2 == 0 else -1
    by = -170 + (bi // 2) * 340
    bid = f"b{bi}"
    MIND["nodes"].append(_n(bid, side * 260, by, name, "rect", color, 120, 48))
    MIND["edges"].append(_e("root", bid, sh="r" if side > 0 else "l", th="l" if side > 0 else "r", type="default"))
    for li, leaf in enumerate(leaves):
        lid = f"{bid}l{li}"
        MIND["nodes"].append(_n(lid, side * 470, by - 60 + li * 64, leaf, "pill", color, 120, 40))
        MIND["edges"].append(_e(bid, lid, sh="r" if side > 0 else "l", th="l" if side > 0 else "r", type="default"))

TEMPLATES: list[dict[str, Any]] = [
    {"id": "blank", "title": "空白画布", "kind": "flowchart", "description": "从零开始", "data": {"nodes": [], "edges": []}},
    {"id": "flow", "title": "【示例】灯塔节剧情流程", "kind": "flowchart", "description": "开始 / 处理 / 判断 / 文档 / 便签 / 分组框", "data": FLOW},
    {"id": "workflow", "title": "【示例】AI 出图工作流", "kind": "workflow", "description": "带输入输出端口的节点工作流", "data": WORKFLOW},
    {"id": "mind", "title": "【示例】雾港世界观脑图", "kind": "mindmap", "description": "中心主题向两侧展开", "data": MIND},
]


def get_templates() -> list[dict[str, Any]]:
    return copy.deepcopy(TEMPLATES)
