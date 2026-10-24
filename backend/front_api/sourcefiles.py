"""Private external bindings are not editable Asset.meta. No source file is owned."""
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy.orm import object_session
from .models import ExternalAssetFile
from .projectpreview import stamp


def external_file(asset):
    session = object_session(asset)
    binding = session.get(ExternalAssetFile, asset.id) if session else None
    if binding is None:
        raise HTTPException(404,'该素材没有文件')
    path, root = Path(binding.path).resolve(), Path(binding.root).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(409,'原地索引文件已移动或丢失；请重新定位，原档案保留')
    if stamp(path) != binding.stamp:
        raise HTTPException(409,'原地索引文件已修改；请审核后导入新版本，原档案保留')
    return path
