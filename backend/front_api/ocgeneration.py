"""OC bindings around the existing generation engine, not a second SD engine."""
from fastapi import HTTPException
from . import models as m,ocstudio as studio


def prepare(session,req,batch):
    if req.oc_profile_id is None:return None
    obj=session.get(m.OCProfile,req.oc_profile_id)
    if obj is None:raise HTTPException(404,'OC档案不存在')
    studio.guard(session,obj,req.oc_expected_version);studio.design(obj,req.oc_design_id)
    current=studio.scope(session,obj)
    if req.world_id not in (None,current['world_id']):raise HTTPException(422,'生成范围与OC归属不同')
    req.world_id=current['world_id']
    row=m.OCGenerationBatch(id=batch,profile_id=obj.id,profile_identity=studio.identity(obj),scope=current,design_id=req.oc_design_id,recipe=req.model_dump())
    session.add(row)
    return row


def attach_output(session,batch,asset,generation,job):
    row=session.get(m.OCGenerationBatch,batch)
    if row is None:return
    obj=session.get(m.OCProfile,row.profile_id) if row.profile_id else None
    if obj is None or studio.identity(obj)!=row.profile_identity or studio.scope(session,obj)!=row.scope or (row.design_id and not any(d['id']==row.design_id for d in obj.designs)):
        job.errors.append('OC或造型归属已变化：生成结果保留在素材库，未自动关联');return
    try:studio.attach(session,obj,'asset',asset.id,role='generated',design_id=row.design_id,generation_id=generation.id,batch=batch,parameters=generation.params)
    except HTTPException:
        job.errors.append('素材已有不同世界观归属，未自动跨世界关联；请手工审核引用')


def bind_job(session,batch,job):
    row=session.get(m.OCGenerationBatch,batch)
    if row:row.job_id=job.id;session.commit()
