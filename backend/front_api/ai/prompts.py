"""把角色卡 / 世界观拼成发给模型的上下文。"""

from __future__ import annotations

import json
import re
from typing import Any


def _fill(text: str, char: str, user: str) -> str:
    return (text or "").replace("{{char}}", char).replace("{{user}}", user).replace("<BOT>", char).replace("<USER>", user)


def build_roleplay_messages(card: Any, history: list[dict[str, str]], user_name: str = "User", max_history: int = 40) -> list[dict[str, str]]:
    char = card.name
    parts = [
        _fill(card.system_prompt, char, user_name)
        or f"你正在进行角色扮演，扮演 {char}。始终保持角色，不要替 {user_name} 说话。",
    ]
    if card.description:
        parts.append(f"【角色设定】\n{_fill(card.description, char, user_name)}")
    if card.personality:
        parts.append(f"【性格】\n{_fill(card.personality, char, user_name)}")
    if card.scenario:
        parts.append(f"【场景】\n{_fill(card.scenario, char, user_name)}")
    if card.mes_example:
        parts.append(f"【对话示例】\n{_fill(card.mes_example, char, user_name)}")
    messages = [{"role": "system", "content": "\n\n".join(parts)}]
    messages.extend(history[-max_history:])
    if card.post_history_instructions:
        messages.append({"role": "system", "content": _fill(card.post_history_instructions, char, user_name)})
    return messages


def build_relation_messages(world: Any, characters: list[Any]) -> list[dict[str, str]]:
    roster = "\n".join(f"- id={c.id} {c.name}：{(c.summary or '')[:200]}" for c in characters)
    return [
        {
            "role": "system",
            "content": (
                "你是世界观设定分析助手。根据设定文本找出角色之间的关系。"
                "只输出 JSON 数组，每项形如 {\"source_id\":1,\"target_id\":2,\"kind\":\"青梅竹马\",\"description\":\"依据\"}，"
                "只能使用给出的角色 id，不要编造文本中没有依据的关系。"
            ),
        },
        {
            "role": "user",
            "content": f"世界观：{world.name}\n\n{world.summary or ''}\n\n{world.content or ''}\n\n角色列表：\n{roster}",
        },
    ]


def parse_relations(text: str, valid_ids: set[int]) -> list[dict[str, Any]]:
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    seen = set()
    for it in items if isinstance(items, list) else []:
        try:
            s, t = int(it["source_id"]), int(it["target_id"])
            kind = str(it.get("kind") or "相关").strip()[:60]
        except (KeyError, TypeError, ValueError):
            continue
        if s == t or s not in valid_ids or t not in valid_ids or (s, t, kind) in seen:
            continue
        seen.add((s, t, kind))
        out.append({"source_id": s, "target_id": t, "kind": kind, "description": str(it.get("description") or "")[:500]})
    return out
