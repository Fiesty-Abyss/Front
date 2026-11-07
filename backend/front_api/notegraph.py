"""Shared note ancestry check for CRUD, move and immutable-version restore."""
from fastapi import HTTPException
from . import models as m


def validate_parent(session, parent_id, note_id=None):
    if parent_id is None:
        return
    if type(parent_id) is not int or parent_id < 1:
        raise HTTPException(422, '父笔记 ID 必须是正整数或 null')
    seen = set()
    current = parent_id
    while current is not None:
        if current == note_id:
            raise HTTPException(422, '不能把笔记移到自身或自己的子页面里')
        if current in seen:
            raise HTTPException(409, '目标目录已有循环，请先修复目录关系')
        seen.add(current)
        node = session.get(m.Note, current)
        if node is None:
            raise HTTPException(422, '父笔记不存在或目录关联已失效')
        current = node.parent_id
