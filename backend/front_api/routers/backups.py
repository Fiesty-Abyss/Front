from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from .. import backups, jobs
from ..config import get_settings

router=APIRouter(prefix='/api/backups',tags=['完整备份与恢复'])


class Create(BaseModel):
    external_asset_ids:list[int]=Field(default_factory=list,max_length=5000)


class Package(BaseModel):
    path:str=Field(min_length=1,max_length=4000)


class Restore(Package):
    confirmed:bool=False
    allow_partial:bool=False


@router.get('')
def listing():
    root=get_settings().data_dir/'backups';items=[]
    if root.exists():
        for path in sorted(root.glob('full-*/manifest.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]:
            try:
                if path.stat().st_size>backups.MAX_MANIFEST:continue
                import json
                data=json.loads(path.read_text(encoding='utf-8'))
                items.append({'id':data['id'],'path':str(path.parent),'status':data['status'],'created_at':data['created_at'],'files':len(data['files'])+1,'issues':len(data['issues'])})
            except (OSError,ValueError,KeyError):continue
    return items


@router.get('/external')
def external(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    import sqlite3
    with sqlite3.connect(get_settings().db_path) as db:
        total=db.execute('SELECT count(*) FROM external_asset_files').fetchone()[0]
        rows=db.execute('SELECT e.asset_id,a.title,e.path FROM external_asset_files e JOIN assets a ON a.id=e.asset_id ORDER BY e.asset_id LIMIT ? OFFSET ?',(limit,offset))
        return {'total':total,'items':[{'id':r[0],'title':r[1],'path':r[2]} for r in rows]}


@router.get('/restores')
def restores():
    import json
    root=get_settings().data_dir/'restores';items=[]
    if root.exists():
        for path in sorted(root.glob('*/restore-report.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]:
            try:
                backups.checked(root,path)
                if path.stat().st_size>backups.MAX_MANIFEST:continue
                value=json.loads(path.read_text(encoding='utf-8'))
                items.append({'path':str(path.parent),'status':value['status'],'restore_id':value.get('restore_id'),'failure_type':value.get('failure_type')})
            except (OSError,ValueError,KeyError):continue
    return items


@router.post('',status_code=202)
def create(body:Create):
    return jobs.start('full-backup','完整数据备份',0,lambda job:backups.create(job,body.external_asset_ids)).to_dict()


@router.post('/preview',status_code=202)
def preview(body:Package):
    def work(job):
        manifest,issues=backups.verify(Path(body.path),job.check)
        job.result={'path':str(Path(body.path).resolve()),'backup_id':manifest['id'],'status':manifest['status'],'files':len(manifest['files'])+1,'bytes':manifest['database']['size']+sum(f['size'] for f in manifest['files']),
                    'references':manifest['references'],'source_issues':manifest['issues'],'verification_issues':issues,'can_restore':not issues,'credentials_notice':manifest['credentials']}
    return jobs.start('backup-verify','恢复前预览与Hash校验',0,work).to_dict()


@router.post('/restore',status_code=202)
def restore(body:Restore):
    if not body.confirmed:raise HTTPException(422,'请先预览并明确确认创建独立恢复副本')
    def work(job):
        try:backups.restore(job,body.path,body.allow_partial)
        except ValueError as exc:
            job.result={'error':str(exc)[:500],'active_data_unchanged':True};raise
    return jobs.start('full-restore','恢复到独立目录',0,work).to_dict()
