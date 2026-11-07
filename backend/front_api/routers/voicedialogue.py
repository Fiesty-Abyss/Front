"""Dialogue editing/manual audio adoption; no TTS requests or model loads."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session, defer
from .. import models as m, versions as v, voicestudio as vs, voiceprojects as vp
from ..crud import get_or_404
from ..db import get_session

router=APIRouter(prefix='/api/voice/projects',tags=['Voice dialogue'])


@router.get('')
def projects(q:str=Query('',max_length=200),limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    query=select(m.VoiceProject)
    if q:query=query.where(m.VoiceProject.title.contains(q,autoescape=True))
    total=session.scalar(select(func.count()).select_from(query.subquery()))
    rows=session.scalars(query.options(defer(m.VoiceProject.notes)).order_by(m.VoiceProject.id.desc()).offset(offset).limit(limit)).all()
    return {'total':total,'items':[vs.serialize(session,obj,False) for obj in rows]}


@router.post('',status_code=201)
def create(body:vp.ProjectDraft,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    if body.world_id:get_or_404(session,m.World,body.world_id)
    obj=m.VoiceProject(title=body.title,world_id=body.world_id,notes=body.notes)
    session.add(obj);session.flush();v.enable(session,obj,'新建配音工程');session.commit()
    return vs.serialize(session,obj)


@router.get('/{project_id}')
def detail(project_id:int,session:Session=Depends(get_session)):
    return vs.serialize(session,get_or_404(session,m.VoiceProject,project_id))


@router.put('/{project_id}')
def edit_project(project_id:int,body:vp.ProjectDraft,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    obj=get_or_404(session,m.VoiceProject,project_id);vs.guard(session,obj,body.expected_uid,body.expected_version)
    if body.world_id!=obj.world_id:
        raise HTTPException(409,'工程归属不可静默迁移；请创建独立工程')
    obj.title=body.title;obj.notes=body.notes
    session.flush();v.record(session,obj);session.commit()
    return vs.serialize(session,obj)


@router.get('/{project_id}/segments')
def listing(project_id:int,archived:bool=False,limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    project=get_or_404(session,m.VoiceProject,project_id);query=vp.active(project_id)
    if archived:query=select(m.VoiceSegment).where(m.VoiceSegment.project_id==project_id,m.VoiceSegment.source['archived'].as_boolean().is_(True))
    total=session.scalar(select(func.count()).select_from(query.subquery()))
    rows=session.scalars(query.order_by(m.VoiceSegment.position,m.VoiceSegment.id).offset(offset).limit(limit)).all()
    return {'project':vs.serialize(session,project),'total':total,'items':[vp.describe(session,obj,True) for obj in rows]}


@router.get('/{project_id}/segments/{segment_id}')
def segment_detail(project_id:int,segment_id:int,session:Session=Depends(get_session)):
    return vp.describe(session,vp.segment(session,get_or_404(session,m.VoiceProject,project_id),segment_id))


@router.post('/{project_id}/segments',status_code=201)
def append(project_id:int,body:vp.SegmentDraft,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body)
    position=session.scalar(select(func.max(m.VoiceSegment.position)).where(m.VoiceSegment.project_id==project_id))
    obj=m.VoiceSegment(project_id=project_id,position=(position+1 if position is not None else 0))
    vp.apply(session,project,obj,body);session.add(obj);session.flush();v.enable(session,obj,'新增台词')
    vp.touch(session,project,'新增台词');session.commit()
    return {'project':vs.serialize(session,project),'segment':vp.describe(session,obj)}


@router.put('/{project_id}/segments/{segment_id}')
def edit(project_id:int,segment_id:int,body:vp.SegmentDraft,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body);obj=vp.segment(session,project,segment_id);vp.editable(obj)
    if body.expected_segment_version!=vs.version_id(session,obj):
        raise HTTPException(409,'台词已被其他窗口修改，请重新加载该片段后合并')
    vp.apply(session,project,obj,body);vp.touch(session,project,'修改台词');session.commit()
    return {'project':vs.serialize(session,project),'segment':vp.describe(session,obj)}


def following(session,project,obj):
    return session.scalar(vp.active(project.id).where(m.VoiceSegment.position>obj.position).order_by(m.VoiceSegment.position,m.VoiceSegment.id).limit(1))


@router.post('/{project_id}/segments/{segment_id}/split')
def split(project_id:int,segment_id:int,body:vp.Split,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body);obj=vp.segment(session,project,segment_id);vp.editable(obj)
    if body.at>=len(obj.text):raise HTTPException(422,'拆分位置必须在正文内部（按Unicode字符计数）')
    session.execute(update(m.VoiceSegment).where(m.VoiceSegment.project_id==project_id,m.VoiceSegment.position>obj.position).values(position=m.VoiceSegment.position+1))
    pieces=[]
    for offset,text in enumerate((obj.text[:body.at],obj.text[body.at:])):
        child=m.VoiceSegment(project_id=project_id,position=obj.position+offset,text=text,profile_id=obj.profile_id,recipe=dict(obj.recipe),source={**obj.source,'archived':False,'split_from':obj.uid})
        session.add(child);session.flush();v.enable(session,child,'拆分台词');pieces.append(child.uid)
    obj.source={**obj.source,'archived':True};vp.touch(session,project,'拆分台词，原片段保留')
    session.commit();return {'project':vs.serialize(session,project),'created':pieces}


@router.post('/{project_id}/segments/{segment_id}/merge-next')
def merge(project_id:int,segment_id:int,body:vp.Mutation,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body);obj=vp.segment(session,project,segment_id);vp.editable(obj)
    other=following(session,project,obj)
    if not other:raise HTTPException(422,'没有下一条台词')
    if obj.source.get('book') or other.source.get('book'):
        raise HTTPException(422,'小说来源片段暂不跨段合并；可独立编辑朗读稿，原文证据保留')
    if obj.recipe!=other.recipe or obj.profile_id!=other.profile_id or obj.source.get('speaker')!=other.source.get('speaker'):
        raise HTTPException(422,'合并前请确认两片段的说话人、声线及参数一致')
    text=obj.text+'\n'+other.text
    if len(text)>20000:raise HTTPException(422,'合并后的片段超过20000字符，请保持分段')
    merged=m.VoiceSegment(project_id=project_id,position=obj.position,text=text,profile_id=obj.profile_id,recipe=dict(obj.recipe),source={**obj.source,'archived':False,'merged_from':[obj.uid,other.uid]})
    session.add(merged);session.flush();v.enable(session,merged,'合并台词')
    for original in (obj,other):original.source={**original.source,'archived':True}
    vp.touch(session,project,'合并台词，原片段及音频保留');session.commit()
    return {'project':vs.serialize(session,project),'segment':vp.describe(session,merged)}


@router.post('/{project_id}/segments/{segment_id}/move')
def move(project_id:int,segment_id:int,body:vp.Move,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body);obj=vp.segment(session,project,segment_id);vp.editable(obj)
    if body.direction==0:raise HTTPException(422,'移动方向须为-1或1')
    if body.direction>0:other=following(session,project,obj)
    else:other=session.scalar(vp.active(project_id).where(m.VoiceSegment.position<obj.position).order_by(m.VoiceSegment.position.desc(),m.VoiceSegment.id.desc()).limit(1))
    if other:
        obj.position,other.position=other.position,obj.position
        vp.touch(session,project,'调整台词顺序')
    session.commit();return {'project':vs.serialize(session,project)}


@router.get('/{project_id}/segments/{segment_id}/renders')
def renders(project_id:int,segment_id:int,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    obj=vp.segment(session,get_or_404(session,m.VoiceProject,project_id),segment_id)
    try:current=vp.fingerprint(session,obj)[0]
    except HTTPException:current=None
    query=select(m.VoiceRender).where(m.VoiceRender.segment_id==obj.id)
    total=session.scalar(select(func.count()).select_from(query.subquery()))
    rows=session.scalars(query.order_by(m.VoiceRender.id.desc()).offset(offset).limit(limit)).all()
    return {'total':total,'items':[vp.render(session,r,current) for r in rows]}


@router.post('/{project_id}/segments/{segment_id}/renders',status_code=201)
def attach(project_id:int,segment_id:int,body:vp.Candidate,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body);obj=vp.segment(session,project,segment_id);vp.editable(obj)
    digest,snapshot=vp.fingerprint(session,obj)
    if body.fingerprint!=digest:raise HTTPException(409,'台词或声线参数已变化，请刷新后关联')
    ref=vs.sample(session,body.audio_ref)
    if not ref:raise HTTPException(422,'请选择音频素材')
    asset=session.get(m.Asset,ref['id'])
    if asset.world_id and asset.world_id!=project.world_id:raise HTTPException(422,'音频素材属于不同世界观')
    audio_version=v.enable(session,asset,'配音候选保留音频版本')
    snapshot.update(origin='manual',audio_ref=ref,audio_version=audio_version,note=body.note)
    result=m.VoiceRender(segment_id=obj.id,fingerprint=digest,snapshot=snapshot,audio_asset_id=ref['id'],status='candidate')
    session.add(result);vp.touch(session,project,'关联手动音频候选');session.commit()
    return {'project':vs.serialize(session,project),'render':vp.render(session,result,digest)}


@router.post('/{project_id}/segments/{segment_id}/renders/{render_id}/accept')
def accept(project_id:int,segment_id:int,render_id:int,body:vp.Mutation,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body);obj=vp.segment(session,project,segment_id);vp.editable(obj)
    candidate=get_or_404(session,m.VoiceRender,render_id)
    if candidate.segment_id!=segment_id:raise HTTPException(404,'候选不属于当前片段')
    current=vp.fingerprint(session,obj)[0]
    if candidate.fingerprint!=current:raise HTTPException(409,'候选对应旧台词或参数，请重新生成或手动关联新版')
    vs.sample(session,candidate.snapshot['audio_ref'])
    asset=session.get(m.Asset,candidate.audio_asset_id) if candidate.audio_asset_id else None
    if not asset or (asset.world_id and asset.world_id!=project.world_id):
        raise HTTPException(409,'音频素材已丢失或世界观归属发生变化')
    session.execute(update(m.VoiceRender).where(m.VoiceRender.segment_id==segment_id,m.VoiceRender.status=='accepted').values(status='candidate'))
    candidate.status='accepted';vp.touch(session,project,'采纳候选 '+candidate.uid);session.commit()
    return {'project':vs.serialize(session,project),'render':vp.render(session,candidate,current)}
