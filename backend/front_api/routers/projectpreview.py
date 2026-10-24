from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import jobs, models as m, projectpreview
from ..crud import get_or_404
from ..db import get_session,new_session
from .importer import _resolve_dir,scan_files

router = APIRouter(prefix='/api/project-previews',tags=['项目只读预览'])


class ScanRequest(BaseModel):
    path: str = Field(min_length=1,max_length=4000)
    recursive: bool = True
    world_id: int | None = None


@router.post('',status_code=202)
def start(req: ScanRequest,session: Session = Depends(get_session)):
    root = _resolve_dir(req.path)
    if req.world_id is not None:
        get_or_404(session,m.World,req.world_id)
    def work(job):
        files,unsupported = scan_files(root,req.recursive)
        with new_session() as worker:
            projectpreview.build(root,files,unsupported,worker,job,req.world_id)
    return jobs.start('project-preview',f'项目只读预览：{root.name}',0,work).to_dict()


def report(report_id):
    try:
        return projectpreview.load(report_id)
    except ValueError as exc:
        raise HTTPException(404,str(exc)) from None


@router.get('/{report_id}')
def listing(report_id: str,limit: int = Query(50,ge=1,le=100),offset: int = Query(0,ge=0)):
    data = report(report_id)
    files = data.pop('files')
    return data | {'items':files[offset:offset+limit]}


def source(report_id,index):
    try:
        return projectpreview.file_of(report(report_id),index)
    except (ValueError,OSError) as exc:
        raise HTTPException(409,str(exc) if isinstance(exc,ValueError) else '原文件不可读') from None


@router.get('/{report_id}/files/{index}')
def detail(report_id: str,index: int):
    item,path = source(report_id,index)
    try:
        return item | projectpreview.text_preview(path)
    except Exception:
        return item | {'text':'','note':'无法读取文本预览；原文件不变'}


@router.get('/{report_id}/files/{index}/image')
def image(report_id: str,index: int):
    item,path = source(report_id,index)
    if item['kind'] != 'drawing' or path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.gif','.bmp'):
        raise HTTPException(415,'该格式没有内嵌图片预览')
    if (item.get('width',0) * item.get('height',0) > 16000000 or path.stat().st_size > 40 * 1024 * 1024):
        raise HTTPException(413,'图片超过本轮内嵌预览限额（1600万像素/40MiB），请仅查看元数据')
    mime = {'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp','.gif':'image/gif','.bmp':'image/bmp'}[path.suffix.lower()]
    return FileResponse(path,media_type=mime,headers={'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})
