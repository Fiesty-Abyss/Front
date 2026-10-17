"""galgame CG 分组：把同一张 CG 的差分（表情、服装、光照等变化）归为一组。

识别规则（按顺序）：
1. 数字后接字母：``ev01a`` ``ev01_b`` ``CG12-c`` → 组 ``ev01`` / 差分 ``a``
2. 带数字的前缀 + 分隔符 + 数字：``ev01_02`` ``ev_12-3`` → 组 ``ev01`` / 差分 ``02``
3. 末尾 4 位以上连续数字，且有兄弟文件共享去掉末 2 位后的前缀：``ev0101 ev0102`` → 组 ``ev01``
4. 显式的差分标记：``ev01_diff2`` ``ev01_sabun3`` ``ev01差分2``
同组还要求分辨率一致（已知时），否则拆成不同组。
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any

_R_MARK = re.compile(r"^(.*?)[_\-\s]*(?:diff|sabun|差分|var)[_\-\s]*(\d+)$", re.I)
_R_LETTER = re.compile(r"^(.*?\d+)[_\-\s]?([a-z])$", re.I)
_R_NUM = re.compile(r"^(.*?\d+)[_\-\s](\d{1,3})$")
_R_TAIL = re.compile(r"^(.*?)(\d{4,})$")


def natural_key(s: str) -> list[Any]:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


@dataclass
class CGItem:
    name: str
    width: int | None = None
    height: int | None = None
    ref: Any = None  # 调用方附带的任意数据（例如 asset id 或文件路径）
    group: str = ""
    variant: str = ""

    @property
    def stem(self) -> str:
        return PurePath(self.name).stem

    @property
    def size(self) -> str | None:
        return f"{self.width}x{self.height}" if self.width and self.height else None


@dataclass
class CGGroup:
    key: str
    size: str | None
    items: list[CGItem] = field(default_factory=list)


def split_variant(stem: str) -> tuple[str, str] | None:
    for rx in (_R_MARK, _R_LETTER, _R_NUM):
        m = rx.match(stem)
        if m and m.group(1).strip("_- "):
            return m.group(1).strip("_- "), m.group(2).lower()
    return None


def group_cgs(items: list[CGItem]) -> list[CGGroup]:
    pending: list[CGItem] = []
    for it in items:
        sv = split_variant(it.stem)
        if sv:
            it.group, it.variant = sv
        else:
            pending.append(it)
    # 规则 3：末尾连续数字，需要有兄弟文件才拆
    tails: dict[str, list[CGItem]] = defaultdict(list)
    for it in pending:
        m = _R_TAIL.match(it.stem)
        if m:
            tails[it.stem[:-2]].append(it)
    for prefix, members in tails.items():
        if len(members) >= 2:
            for it in members:
                it.group, it.variant = prefix, it.stem[-2:]
    for it in items:
        if not it.group:
            it.group, it.variant = it.stem, ""

    buckets: dict[tuple[str, str | None], CGGroup] = {}
    for it in items:
        key = (it.group.lower(), it.size)
        buckets.setdefault(key, CGGroup(key=it.group, size=it.size)).items.append(it)
    # 同名不同分辨率的组加上分辨率后缀区分
    names = defaultdict(int)
    for (g, _s) in buckets:
        names[g] += 1
    groups = []
    for (g, s), grp in buckets.items():
        if names[g] > 1 and s:
            grp.key = f"{grp.key}@{s}"
        grp.items.sort(key=lambda x: natural_key(x.variant or x.stem))
        groups.append(grp)
    groups.sort(key=lambda gr: natural_key(gr.key))
    return groups


def groups_to_json(groups: list[CGGroup]) -> list[dict[str, Any]]:
    return [
        {
            "key": g.key,
            "size": g.size,
            "count": len(g.items),
            "items": [{"name": i.name, "variant": i.variant, "ref": i.ref} for i in g.items],
        }
        for g in groups
    ]
