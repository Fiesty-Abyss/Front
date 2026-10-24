"""Image capability contracts, OC generation links and two-image comparison."""
import io
import json
import uuid
from datetime import datetime,timezone
from types import SimpleNamespace
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File,Form,Query
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from .. import models as m,jobs,ocstudio as studio,ocgeneration,sdgen,imageapi,versions
from ..db import get_session,new_session
from ..config import get_settings
from ..crud import get_or_404
from ..ingest import ingest,ingest_stream,make_thumb
from .assets import _file_of
from .versions import revision,media_path

router=APIRouter(tags=['OC图像'])


@router.get('/api/oc-image-services')
def services(session:Session=Depends(get_session)):
    settings=get_settings()
    return {'local':[{'id':'webui','name':'WebUI / Forge','configured':bool(settings.sd_webui_url),'supports':['checkpoint','loras','negative','seed','steps','cfg','sampler','size']},
                     {'id':'comfyui','name':'ComfyUI','configured':bool(settings.comfyui_url),'supports':['checkpoint','loras','negative','seed','steps','cfg','sampler','size','workflow']}],
            'items':[{'id':s.id,'name':s.name,'model':s.model,'provider_id':s.provider_id,'legacy_b64':s.legacy_b64,'last_success':s.verified_at,'supports':['prompt','size'],'contract':'用户明确登记的Images API；未自动推断聊天服务能力'} for s in session.scalars(select(m.ImageService))]}


class Contract(BaseModel):
    provider_id:int=Field(ge=1)
    name:str=Field(min_length=1,max_length=100)
    model:str=Field(min_length=1,max_length=200)
    confirmed_images_api:bool=False
    legacy_b64:bool=False


@router.post('/api/oc-image-services',status_code=201)
def register(body:Contract,session:Session=Depends(get_session)):
    if not body.confirmed_images_api:raise HTTPException(422,'请先核对服务文档，明确确认支持Images API与所选图像模型')
    get_or_404(session,m.AIProviderConfig,body.provider_id)
    obj=m.ImageService(**body.model_dump(exclude={'confirmed_images_api'}));session.add(obj);session.commit();return {'id':obj.id}


class ApiRun(BaseModel):
    model_config=ConfigDict(extra='forbid')
    service_id:int=Field(ge=1)
    positive:str=Field(min_length=1,max_length=32000)
    size:str=Field(default='1024x1024',pattern=r'^\d{2,4}x\d{2,4}$')
    count:int=Field(default=1,ge=1,le=8)
    design_id:str|None=None
    expected_version:int=Field(ge=1)


@router.post('/api/oc/{profile_id}/generate-api')
def generate_api(profile_id:int,body:ApiRun,session:Session=Depends(get_session)):
    obj=get_or_404(session,m.OCProfile,profile_id);studio.guard(session,obj,body.expected_version);studio.design(obj,body.design_id)
    service=get_or_404(session,m.ImageService,body.service_id);provider=get_or_404(session,m.AIProviderConfig,service.provider_id)
    if not body.positive.strip():raise HTTPException(422,'提示词不能为空')
    w,h=map(int,body.size.split('x'))
    if not (64<=w<=4096 and 64<=h<=4096):raise HTTPException(422,'尺寸超出64–4096范围；实际支持尺寸由服务决定')
    batch=uuid.uuid4().hex[:12];scope=studio.scope(session,obj)
    row=m.OCGenerationBatch(id=batch,profile_id=obj.id,profile_identity=studio.identity(obj),scope=scope,design_id=body.design_id,recipe={'backend':'images-api',**body.model_dump(),'model':service.model})
    session.add(row)
    provider=SimpleNamespace(**{k:getattr(provider,k) for k in ['id','base_url','api_key','timeout']})
    service=SimpleNamespace(**{k:getattr(service,k) for k in ['id','model','legacy_b64','created_at']})
    profile_title=obj.title
    session.commit()
    # Capture this explicitly selected endpoint in memory; don't persist credential material.
    pid,service_identity=provider.id,studio.identity(service)
    def work(job):
        job.result={'batch':batch,'items':[]}
        for i in range(body.count):
            job.check();data,revised=imageapi.generate(provider,service,body.positive,body.size,job.check);job.check()
            from PIL import Image
            try:
                with Image.open(io.BytesIO(data)) as img:
                    if img.width*img.height>32_000_000:raise ValueError()
                    extension={'PNG':'png','JPEG':'jpg','WEBP':'webp','GIF':'gif'}.get(img.format)
                    if not extension:raise ValueError()
                    img.verify()
            except Exception:raise sdgen.BackendError('API返回图像无效或超过3200万像素上限') from None
            with new_session() as ses:
                asset,created=ingest(ses,data,f'oc-{batch}-{i}.{extension}',kind='ai_image',title=f'{profile_title} · API生成 {i+1}',world_id=scope['world_id'],extra_meta={'generation':{'batch':batch,'backend':'images-api'}})
                params={'backend':'images-api','service_id':service.id,'provider_id':pid,'model':service.model,'prompt':body.positive,'revised_prompt':revised,'requested_size':body.size,'actual_size':f'{asset.width}x{asset.height}'}
                gen=m.Generation(asset_id=asset.id,params=params,batch=batch);ses.add(gen);ses.flush();ocgeneration.attach_output(ses,batch,asset,gen,job)
                current=ses.get(m.ImageService,service.id)
                if current and studio.identity(current)==service_identity:current.verified_at=datetime.now(timezone.utc).isoformat()
                ses.commit()
                if created:make_thumb(asset.id,data)
                job.result['items'].append({'asset_id':asset.id,'generation_id':gen.id});job.step('图像已保存')
    job=jobs.start('generate',f'OC图像API：{profile_title}',body.count,work);ocgeneration.bind_job(session,batch,job);return job.to_dict()


@router.get('/api/oc/{profile_id}/batches')
def batches(profile_id:int,offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    obj=get_or_404(session,m.OCProfile,profile_id)
    stmt=select(m.OCGenerationBatch).where(m.OCGenerationBatch.profile_id==obj.id,m.OCGenerationBatch.profile_identity==studio.identity(obj))
    total=session.scalar(select(func.count()).select_from(stmt.subquery()))
    items=[]
    for r in session.scalars(stmt.order_by(m.OCGenerationBatch.created_at.desc()).offset(offset).limit(20)):
        job=jobs.get(r.job_id) if r.job_id else None
        items.append({'id':r.id,'design_id':r.design_id,'recipe':r.recipe,'created_at':r.created_at,'job':job.to_dict() if job else None,'notice':None if job else '任务历史不可用；保留配方，可明确重新提交'})
    return {'items':items,'total':total}


@router.post('/api/oc/{profile_id}/manual-image')
def manual(profile_id:int,file:UploadFile=File(...),expected_version:int=Form(...),design_id:str|None=Form(None),allow_cross_world:bool=Form(False),parameters:str=Form('{}'),session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');obj=get_or_404(session,m.OCProfile,profile_id);studio.guard(session,obj,expected_version);studio.design(obj,design_id)
    if len(parameters.encode())>65536:raise HTTPException(413,'手工参数超过64KiB')
    try:params=json.loads(parameters);assert isinstance(params,dict)
    except (ValueError,AssertionError):raise HTTPException(422,'参数应为JSON对象') from None
    asset,created=ingest_stream(session,file.file,file.filename or 'manual.png',kind='reference',world_id=studio.scope(session,obj)['world_id'])
    if not asset.width or asset.width*asset.height>32_000_000:raise HTTPException(422,'请选择3200万像素内可解码图片；绘画工程请使用素材库引用')
    gen=m.Generation(asset_id=asset.id,params={'origin':'manual',**params});session.add(gen);session.flush()
    studio.attach(session,obj,'asset',asset.id,role='manual-image',design_id=design_id,allow_cross_world=allow_cross_world,generation_id=gen.id,parameters=gen.params)
    session.commit()
    if created:make_thumb(asset.id,_file_of(asset))
    return {'asset_id':asset.id,'reference_id':obj.references[-1]['id']}


def image_ref(session,profile_id,rid):
    obj=get_or_404(session,m.OCProfile,profile_id);ref=next((r for r in obj.references if r['id']==rid and r['kind']=='asset'),None)
    if not ref:raise HTTPException(404,'图片引用不存在')
    asset,status=studio.reference_status(session,obj,ref)
    if status!='ok':raise HTTPException(409,status)
    if not asset.width:raise HTTPException(422,'引用不是可识别图片')
    return obj,ref,asset


def image_path(session,profile_id,rid):
    _,ref,asset=image_ref(session,profile_id,rid)
    return reference_path(session,ref,asset)


def reference_path(session,ref,asset):
    if ref.get('asset_version'):
        _,_,payload=revision(session,'asset',asset.id,ref['asset_version'])
        if payload.get('file_path'):return media_path(payload['file_path']),payload.get('mime')
    if ref.get('sha256')!=asset.sha256:raise HTTPException(409,'原地索引图片已更新，历史原件未托管')
    return _file_of(asset),asset.mime


@router.get('/api/oc/{profile_id}/images/{rid}/file')
def image_file(profile_id:int,rid:str,download:bool=False,session:Session=Depends(get_session)):
    path,mime=image_path(session,profile_id,rid)
    _,ref,asset=image_ref(session,profile_id,rid)
    return FileResponse(path,media_type=mime,filename=(asset.original_name or path.name) if download else None,headers={'X-Content-Type-Options':'nosniff'})


@router.get('/api/oc/{profile_id}/compare')
def compare(profile_id:int,left:str,right:str,session:Session=Depends(get_session)):
    out=[]
    for rid in [left,right]:
        _,ref,asset=image_ref(session,profile_id,rid);params=ref.get('parameters')
        if params is None:
            gen=session.get(m.Generation,ref['generation_id']) if ref.get('generation_id') else None
            params=gen.params if gen and gen.asset_id==asset.id else (asset.meta or {}).get('sd',{})
        out.append({'reference_id':rid,'asset_id':asset.id,'title':asset.title,'parameters':params,'sha256':ref.get('sha256'),'size':[asset.width,asset.height]})
    keys=set(out[0]['parameters'])|set(out[1]['parameters'])
    return {'items':out,'differences':[{'field':k,'left':out[0]['parameters'].get(k),'right':out[1]['parameters'].get(k)} for k in sorted(keys) if out[0]['parameters'].get(k)!=out[1]['parameters'].get(k)]}
