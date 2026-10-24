from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import Session, defer
from .. import models as m, schemas as s, extractionreview as review
from ..db import get_session
from ..crud import get_or_404
from ..ai import AIProvider
from .ai import provider_dep
from .aitools import apply_characters

router=APIRouter(prefix='/api/ai/extract/reviews',tags=['抽取证据审核'])


class Retry(BaseModel):
    confirm_send:bool=False


class Decision(s.ExtractedCharacter):
    candidate_name:str=Field(min_length=1,max_length=200)


class Approval(BaseModel):
    characters:list[Decision]=Field(min_length=1,max_length=1000)
    relation_keys:list[str]=Field(default_factory=list,max_length=5000)
    update_existing:bool=False


@router.get('')
def listing(world_id:int,asset_id:int|None=None,limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    stmt=select(m.ExtractionBatch).where(m.ExtractionBatch.world_id==world_id)
    if asset_id:stmt=stmt.where(m.ExtractionBatch.asset_id==asset_id)
    rows=session.scalars(stmt.order_by(m.ExtractionBatch.created_at.desc()).offset(offset).limit(limit)).all()
    return {'total':session.scalar(select(func.count()).select_from(stmt.subquery())),
            'items':[{'id':r.id,'status':r.status,'asset_id':r.asset_id,'work_id':r.work_id,'created_at':r.created_at,'model':r.model,'text_hash':r.text_hash} for r in rows]}


@router.get('/{batch_id}')
def detail(batch_id:str,session:Session=Depends(get_session)):
    b=get_or_404(session,m.ExtractionBatch,batch_id)
    if review.reconcile(b):session.commit()
    units=session.scalars(select(m.ExtractionUnit).where(m.ExtractionUnit.batch_id==b.id).options(defer(m.ExtractionUnit.content),defer(m.ExtractionUnit.result)).order_by(m.ExtractionUnit.id)).all()
    return {'id':b.id,'asset_id':b.asset_id,'world_id':b.world_id,'work_id':b.work_id,'revision':b.revision,'text_hash':b.text_hash,'chapter_indices':b.chapter_indices,'provider':b.provider,'model':b.model,'job_id':b.job_id,'status':b.status,
            'units':[{'id':u.id,'chapter_index':u.chapter_index,'chapter_title':u.chapter_title,'start':u.start,'status':u.status,'error':u.error} for u in units],
            'characters':review.candidates(session,b)}


@router.get('/{batch_id}/compare/{previous_id}')
def compare(batch_id:str,previous_id:str,session:Session=Depends(get_session)):
    b=get_or_404(session,m.ExtractionBatch,batch_id);old=get_or_404(session,m.ExtractionBatch,previous_id)
    if (b.world_id,b.work_id,b.asset_id,b.asset_created_at)!=(old.world_id,old.work_id,old.asset_id,old.asset_created_at):raise HTTPException(422,'仅比较同世界观、作品及原小说的抽取批次')
    aa=review.candidates(session,old);bb=review.candidates(session,b)
    an={c['name'] for c in aa};bn={c['name'] for c in bb}
    def edges(chars):return {(c['name'],r['target'],r['kind']) for c in chars for r in c['relations']}
    ae,be=edges(aa),edges(bb)
    return {'added':sorted(bn-an),'absent':sorted(an-bn),'relations_added':sorted(be-ae),'relations_absent':sorted(ae-be),
            'same_scope':b.chapter_indices==old.chapter_indices,'notice':'仅比较候选结果，不代表设定事实增删；章节范围、模型或失败片段差异均可能影响结果'}


@router.post('/{batch_id}/resume')
def resume(batch_id:str,body:Retry,session:Session=Depends(get_session),provider:AIProvider=Depends(provider_dep)):
    if not body.confirm_send:raise HTTPException(422,'需再次确认剩余章节发送给当前服务')
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    b=get_or_404(session,m.ExtractionBatch,batch_id);review.validate_scope(session,b)
    review.reconcile(b)
    if b.status not in ('partial','interrupted','cancelled'):raise HTTPException(409,'此批次不能重复启动')
    if not provider.available():raise HTTPException(503,'请先配置AI对话服务')
    if str(getattr(provider,'model','') or '')!=b.model or review.service_fingerprint(provider)!=b.endpoint_id:raise HTTPException(409,'服务地址或模型已变化，请创建新的批次以保持来源可追踪')
    return review.enqueue(session,b,provider)


@router.post('/{batch_id}/apply')
def apply(batch_id:str,body:Approval,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    b=get_or_404(session,m.ExtractionBatch,batch_id);review.validate_scope(session,b)
    if b.status in ('queued','running'):raise HTTPException(409,'批次仍在处理，请结束后审核')
    available={c['name']:c for c in review.candidates(session,b)}
    if len({c.candidate_name for c in body.characters})!=len(body.characters):raise HTTPException(422,'候选重复')
    selected=[];existing_map={};already=[]
    for decision in body.characters:
        candidate=available.get(decision.candidate_name)
        if not candidate:raise HTTPException(422,'候选没有可核验的正文证据')
        if candidate['approved']:
            char=session.get(m.Character,candidate['character_id']) if candidate['character_id'] else None
            if not char or char.world_id!=b.world_id:raise HTTPException(409,'已审核人物已失效或归属变化，请新建批次重新确认')
            already.append(char.id);existing_map[decision.candidate_name]=char.id
            previous=session.scalars(select(m.ExtractionEvidence).where(m.ExtractionEvidence.batch_id==b.id,m.ExtractionEvidence.entity_kind=='character',m.ExtractionEvidence.entity_id==char.id)).all()
            for proof in candidate['evidence']:
                value=proof|{'candidate_name':decision.candidate_name}
                if not any(e.evidence==value for e in previous):session.add(m.ExtractionEvidence(batch_id=b.id,entity_kind='character',entity_id=char.id,entity_created_at=review.identity_time(char.created_at),evidence=value))
            continue
        cid=decision.existing_id
        if cid is not None:
            char=get_or_404(session,m.Character,cid)
            if char.world_id!=b.world_id:raise HTTPException(422,'禁止跨世界观自动合并人物')
        else:
            same=list(session.scalars(select(m.Character).where(m.Character.world_id==b.world_id,m.Character.name==decision.name)))
            if len(same)>1:raise HTTPException(409,'同世界观有多个同名人物，请明确选择要关联的ID')
            if same:cid=same[0].id
        selected.append((decision,candidate,cid))
    names=[x.name for x,_,_ in selected]
    if len(set(names))!=len(names):raise HTTPException(422,'多个候选改为同名时，请分批明确关联同一已有人物')
    payload=s.ExtractApply(world_id=b.world_id,work_id=b.work_id,relations=False,update_existing=body.update_existing,
        source=f'审核批次 {b.id}',characters=[s.ExtractedCharacter(**(d.model_dump(exclude={'candidate_name','existing_id','relations'})|{'existing_id':cid,'relations':[]})) for d,_,cid in selected])
    result=apply_characters(payload,session)
    created=iter(result['created'])
    for d,c,cid in selected:
        cid=cid if cid is not None else next(created);existing_map[d.candidate_name]=cid
        char=session.get(m.Character,cid)
        session.add(m.ExtractionApproval(batch_id=b.id,candidate_name=d.candidate_name,character_id=cid))
        for proof in c['evidence']:
            session.add(m.ExtractionEvidence(batch_id=b.id,entity_kind='character',entity_id=cid,entity_created_at=review.identity_time(char.created_at),evidence=proof|{'candidate_name':d.candidate_name}))
    valid_edges={r['key']:(c['name'],r) for c in available.values() for r in c['relations']}
    if set(body.relation_keys)-valid_edges.keys():raise HTTPException(422,'关系缺少可核验证据')
    rel_count=0
    for key in set(body.relation_keys):
        source,r=valid_edges[key];sid=existing_map.get(source);tid=existing_map.get(r['target'])
        if not sid or not tid or sid==tid:raise HTTPException(422,'关系两端需同时明确审核（含已有角色）')
        src=session.get(m.Character,sid);dst=session.get(m.Character,tid)
        if not src or not dst or src.world_id!=b.world_id or dst.world_id!=b.world_id:raise HTTPException(409,'关系人物已失效或归属改变')
        rel=session.scalar(select(m.Relation).where(m.Relation.kind==r['kind'],or_(and_(m.Relation.source_id==sid,m.Relation.target_id==tid),and_(m.Relation.bidirectional.is_(True),m.Relation.source_id==tid,m.Relation.target_id==sid))).limit(1))
        if not rel:
            rel=m.Relation(source_id=sid,target_id=tid,kind=r['kind'],description=r['evidence']['quote'],bidirectional=False,ai_suggested=True,confirmed=False)
            session.add(rel);session.flush();rel_count+=1
        proof=r['evidence']|{'candidate_key':key}
        previous=session.scalars(select(m.ExtractionEvidence).where(m.ExtractionEvidence.batch_id==b.id,m.ExtractionEvidence.entity_kind=='relation',m.ExtractionEvidence.entity_id==rel.id)).all()
        if not any(p.evidence==proof for p in previous):session.add(m.ExtractionEvidence(batch_id=b.id,entity_kind='relation',entity_id=rel.id,entity_created_at=review.identity_time(rel.created_at),evidence=proof))
    session.commit()
    return result|{'relations':rel_count,'already':already,'mapping':existing_map}


@router.get('/evidence/{kind}/{entity_id}')
def evidence(kind:str,entity_id:int,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    model={'character':m.Character,'relation':m.Relation}.get(kind)
    if not model:raise HTTPException(422,'仅人物或关系证据')
    obj=get_or_404(session,model,entity_id)
    rows=session.scalars(select(m.ExtractionEvidence).where(m.ExtractionEvidence.entity_kind==kind,m.ExtractionEvidence.entity_id==entity_id,m.ExtractionEvidence.entity_created_at==review.identity_time(obj.created_at)).order_by(m.ExtractionEvidence.id).offset(offset).limit(limit)).all()
    batches={b.id:b for b in session.scalars(select(m.ExtractionBatch).where(m.ExtractionBatch.id.in_({r.batch_id for r in rows})))}
    return [{'batch_id':r.batch_id,'evidence':r.evidence,'asset_id':batches[r.batch_id].asset_id,'world_id':batches[r.batch_id].world_id,'work_id':batches[r.batch_id].work_id,'revision':batches[r.batch_id].revision,'text_hash':batches[r.batch_id].text_hash} for r in rows]
