"""OC drafts reuse encyclopedia identities, asset references, global tags and versions."""
import json
import uuid
from fastapi import HTTPException
from . import models as m,versions

TARGETS={'asset':m.Asset,'note':m.Note,'prompt':m.Prompt,'model':m.SDModel}


def identity(obj):return obj.created_at.replace(tzinfo=None).isoformat()


def character(session,profile):return session.get(m.Character,profile.character_id) if profile.character_id else None


def scope(session,profile):
    c=character(session,profile)
    return {'character_id':c.id if c else None,'world_id':c.world_id if c else None,'work_id':c.work_id if c else None}


def revision(session,profile):
    h=versions.head(session.connection(),'oc',profile.id)
    r=versions.latest(session.connection(),h['generation']) if h else None
    return r['id'] if r else 0


def guard(session,profile,expected):
    if revision(session,profile)!=expected:raise HTTPException(409,'创作档案已更新，请重新加载并比较版本')


def design(profile,design_id):
    if design_id is None:return None
    result=next((d for d in profile.designs if d['id']==design_id),None)
    if result is None:raise HTTPException(422,'造型ID不属于当前OC')
    return result


def normalize(fields,designs):
    if len(fields)>100 or any(not k.strip() or len(k)>80 or len(v)>10000 for k,v in fields.items()):raise HTTPException(422,'自定义字段最多100项，名称80字、单值10000字')
    out=[];ids=set()
    for d in designs:
        value=d.model_dump();value['id']=value.get('id') or uuid.uuid4().hex
        if value['id'] in ids:raise HTTPException(422,'造型ID重复')
        ids.add(value['id'])
        if len(value['fields'])>100 or any(not k.strip() or len(k)>80 or len(v)>10000 for k,v in value['fields'].items()):raise HTTPException(422,'造型字段超出上限')
        out.append(value)
    if len(json.dumps([fields,out],ensure_ascii=False).encode())>256*1024:raise HTTPException(413,'设计草稿超过256KiB，请将长文关联到笔记')
    return out


def reference_status(session,profile,ref):
    target=session.get(TARGETS.get(ref['kind']),ref['entity_id']) if ref['kind'] in TARGETS else None
    if not target or identity(target)!=ref['identity']:return None,'原记录已删除或ID已复用'
    world=scope(session,profile)['world_id'];target_world=getattr(target,'world_id',None)
    if target_world is not None and target_world!=world and not (ref.get('allow_cross_world') and ref.get('approved_scope')==world and ref.get('approved_target_world')==target_world):return None,'资料归属不同；需明确重新确认跨世界引用'
    return target,'ok'


def attach(session,profile,kind,entity_id,role='reference',design_id=None,allow_cross_world=False,as_cover=False,**extra):
    design(profile,design_id)
    model=TARGETS.get(kind);target=session.get(model,entity_id) if model else None
    if not target:raise HTTPException(404,'引用资料不存在')
    world=scope(session,profile)['world_id'];other=getattr(target,'world_id',None)
    if other is not None and other!=world and not allow_cross_world:raise HTTPException(422,'跨世界引用需要明确确认，不按名称自动关联')
    if as_cover and (kind!='asset' or not target.width):raise HTTPException(422,'封面请选择可识别图片素材')
    key=(kind,entity_id,role,design_id)
    old=next((r for r in profile.references if (r['kind'],r['entity_id'],r['role'],r.get('design_id'))==key and r['identity']==identity(target)),None)
    value={'id':old['id'] if old else uuid.uuid4().hex,'kind':kind,'entity_id':entity_id,'identity':identity(target),'role':role,'design_id':design_id,'allow_cross_world':allow_cross_world,'approved_scope':world,'approved_target_world':other,**extra}
    if kind=='asset':
        value['asset_version']=versions.enable(session,target,'OC引用时素材快照')
        value['sha256']=target.sha256
    if len(profile.references)>=2000 and not old:raise HTTPException(413,'单档案引用超过2000，请整理收藏集')
    references=[r for r in profile.references if r['id']!=value['id']]+[value]
    if len(json.dumps(references,ensure_ascii=False).encode())>8*1024*1024:raise HTTPException(413,'档案引用元数据超过8MiB，请拆分整理收藏集')
    profile.references=references
    if as_cover:profile.cover_asset_id=entity_id
    return value
