"""Lexical path validation before resolution; never traverse reparse points."""
import os
import stat
from pathlib import Path, PurePosixPath


def plain_path(value):
    path = Path(os.path.abspath(os.path.expanduser(str(value))))
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('路径包含符号链接或Windows重解析点，请选择实际目录')
    return path


def preview_file(root, relative):
    name = PurePosixPath(relative.replace('\\', '/'))
    if name.is_absolute() or not name.parts or any(p in ('..', '.') or ':' in p for p in name.parts):
        raise ValueError('预览文件路径不安全')
    base = plain_path(root)
    path = plain_path(base.joinpath(*name.parts))
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError('原文件已移动、失效或不支持文件预览')
    return path
