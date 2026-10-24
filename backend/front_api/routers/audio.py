import json,uuid,math,wave
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import Response
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,func,or_,delete
from sqlalchemy.orm import Session,defer
from .. import models as m,jobs,projectpreview,subtitles
from ..db import get_session,new_session
from ..crud import get_or_404,resolve_tags,tag_descendants
from ..ocstudio import identity
from ..referenceimports import link
from ..config import get_settings
from ..ingest import decode_text
from .assets import _file_of

router=APIRouter(prefix='/api/audio',tags=['Audio Library'])


class Album(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    category:str=Field(default='音频收藏',max_length=80)
    world_id:int|None=None
    work_id:int|None=None
    character_id:int|None=None
    cover_asset_id:int|None=None
    favorite:bool=False
    stars:int=Field(default=0,ge=0,le=5)
    preference:int=Field(default=0,ge=0,le=100)
    notes:str=Field(default='',max_length=30000)
    tag_ids:list[int]=Field(default_factory=list,max_length=100)


def validate_album(session,body):
    for key,model in [('world_id',m.World),('work_id',m.Work),('character_id',m.Character),('cover_asset_id',m.Asset)]:
        value=getattr(body,key)
        if value is not None:get_or_404(session,model,value)
    if body.character_id:
        char=session.get(m.Character,body.character_id)
        if char.world_id is not None and char.world_id!=body.world_id:raise HTTPException(422,'关联角色需选择相同世界观，不按名字跨世界关联')


def album_dict(row):
    keys=('id','title','category','collection_id','world_id','work_id','character_id','cover_asset_id','favorite','stars','preference','notes','updated_at')
    return {k:getattr(row,k) for k in keys}|{'tags':[{'id':t.id,'name':t.name,'color':t.color} for t in row.tags]}


@router.get('/albums')
def albums(q:str='',category:str='',favorite:bool=False,offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    stmt=select(m.AudioAlbum)
    if q:stmt=stmt.where(m.AudioAlbum.title.contains(q,autoescape=True))
    if category:stmt=stmt.where(m.AudioAlbum.category==category)
    if favorite:stmt=stmt.where(m.AudioAlbum.favorite.is_(True))
    total=session.scalar(select(func.count()).select_from(stmt.subquery()))
    return {'total':total,'items':[album_dict(a) for a in session.scalars(stmt.order_by(m.AudioAlbum.favorite.desc(),m.AudioAlbum.updated_at.desc()).offset(offset).limit(30))]}


@router.post('/albums',status_code=201)
def create_album(body:Album,session:Session=Depends(get_session)):
    validate_album(session,body);col=m.Collection(name=body.title,work_id=body.work_id,description='Audio Library播放列表；共用素材引用');session.add(col);session.flush()
    row=m.AudioAlbum(**body.model_dump(exclude={'tag_ids'}),collection_id=col.id,tags=resolve_tags(session,body.tag_ids));session.add(row);session.commit();return album_dict(row)


@router.put('/albums/{album_id}')
def update_album(album_id:int,body:Album,expected_updated_at:str,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');row=get_or_404(session,m.AudioAlbum,album_id)
    if row.updated_at.isoformat()!=expected_updated_at:raise HTTPException(409,'专辑已更新，请重新加载')
    validate_album(session,body)
    for k,v in body.model_dump(exclude={'tag_ids'}).items():setattr(row,k,v)
    row.tags=resolve_tags(session,body.tag_ids);session.commit();return album_dict(row)


class TrackLink(BaseModel):
    asset_ids:list[int]=Field(min_length=1,max_length=500)
    allow_cross_scope:bool=False


@router.post('/albums/{album_id}/tracks')
def add_tracks(album_id:int,body:TrackLink,session:Session=Depends(get_session)):
    row=get_or_404(session,m.AudioAlbum,album_id)
    if row.collection_id is None:raise HTTPException(409,'关联收藏集已删除，保留专辑档案，请新建播放列表')
    for aid in dict.fromkeys(body.asset_ids):
        asset=get_or_404(session,m.Asset,aid)
        if asset.kind!='audio':raise HTTPException(422,'请选择音频素材')
        if not body.allow_cross_scope and any(getattr(asset,k) is not None and getattr(asset,k)!=getattr(row,k) for k in ('world_id','work_id')):raise HTTPException(422,'不同作品或世界观的音频需要明确允许引用')
        link(session,row.collection_id,aid)
    session.commit();return {'linked':len(set(body.asset_ids))}


@router.delete('/albums/{album_id}/tracks/{asset_id}')
def unlink(album_id:int,asset_id:int,session:Session=Depends(get_session)):
    row=get_or_404(session,m.AudioAlbum,album_id);session.execute(delete(m.collection_assets).where(m.collection_assets.c.collection_id==row.collection_id,m.collection_assets.c.asset_id==asset_id));session.commit();return {'source_deleted':False}


@router.get('/tracks')
def tracks(q:str='',album_id:int|None=None,tag:int|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),session:Session=Depends(get_session)):
    stmt=select(m.Asset).where(m.Asset.kind=='audio')
    order=[m.Asset.id.desc()]
    if album_id:
        album=get_or_404(session,m.AudioAlbum,album_id)
        stmt=stmt.join(m.collection_assets,m.collection_assets.c.asset_id==m.Asset.id).where(m.collection_assets.c.collection_id==album.collection_id);order=[m.collection_assets.c.position,m.Asset.id]
    if q:
        stmt=stmt.where(or_(m.Asset.title.contains(q,autoescape=True),func.coalesce(func.json_extract(m.Asset.meta,'$.file.artist'),'').contains(q,autoescape=True),func.coalesce(func.json_extract(m.Asset.meta,'$.file.album'),'').contains(q,autoescape=True)))
    if tag:stmt=stmt.where(m.Asset.tags.any(m.Tag.id.in_(tag_descendants(session,tag))))
    total=session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=session.scalars(stmt.options(defer(m.Asset.content),defer(m.Asset.description)).order_by(*order).offset(offset).limit(limit))
    return {'total':total,'items':[{'id':a.id,'identity':identity(a),'sha256':a.sha256,'title':a.title,'original_name':a.original_name,'mime':a.mime,'size':a.size,'file':(a.meta or {}).get('file',{}),'world_id':a.world_id,'work_id':a.work_id,'tags':[{'id':t.id,'name':t.name} for t in a.tags]} for a in rows]}


def audio_asset(session,aid):
    asset=get_or_404(session,m.Asset,aid)
    if asset.kind!='audio':raise HTTPException(422,'素材不是音频')
    return asset


def state_dict(session,asset):
    state=session.get(m.AudioState,asset.id)
    if state is None:return {'asset_id':asset.id,'asset_identity':identity(asset),'sha256':asset.sha256,'position':0,'rate':1,'loop':False,'notes':'','bookmarks':[],'subtitles':[],'history':[],'revision':0,'source_changed':False}
    return {k:getattr(state,k) for k in ('asset_id','position','rate','loop','notes','bookmarks','subtitles','history','revision')}|{'asset_identity':identity(asset),'sha256':asset.sha256,'source_changed':state.content_sha!=asset.sha256}


@router.get('/tracks/{asset_id}/state')
def state(asset_id:int,session:Session=Depends(get_session)):return state_dict(session,audio_asset(session,asset_id))


class Bookmark(BaseModel):
    id:str=Field(min_length=1,max_length=40)
    position:float=Field(ge=0,le=31536000,allow_inf_nan=False)
    label:str=Field(default='',max_length=500)


class State(BaseModel):
    model_config=ConfigDict(extra='forbid')
    asset_identity:str
    sha256:str|None
    expected_revision:int=Field(ge=0)
    position:float|None=Field(default=None,ge=0,le=31536000,allow_inf_nan=False)
    rate:float|None=Field(default=None,ge=.5,le=3,allow_inf_nan=False)
    loop:bool|None=None
    notes:str|None=Field(default=None,max_length=30000)
    bookmarks:list[Bookmark]|None=Field(default=None,max_length=500)
    subtitle_asset_ids:list[int]|None=Field(default=None,max_length=20)
    confirm_source_change:bool=False


@router.put('/tracks/{asset_id}/state')
def save_state(asset_id:int,body:State,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');asset=audio_asset(session,asset_id)
    if body.asset_identity!=identity(asset) or body.sha256!=asset.sha256:raise HTTPException(409,'音频身份或内容已变化，请重新打开')
    row=session.get(m.AudioState,asset_id)
    if (row.revision if row else 0)!=body.expected_revision:raise HTTPException(409,'续听资料已在其他窗口更新，请重新加载')
    if row and row.content_sha!=asset.sha256:
        if not body.confirm_source_change:raise HTTPException(409,'音频已换版，旧进度保留；请明确确认开始新版续听')
        row.history=[*row.history,{'sha256':row.content_sha,'position':row.position}][-20:];row.position=0;row.content_sha=asset.sha256
    if row is None:row=m.AudioState(asset_id=asset_id,content_sha=asset.sha256);session.add(row)
    for key in ('position','rate','loop','notes'):
        if getattr(body,key) is not None:setattr(row,key,getattr(body,key))
    if body.bookmarks is not None:
        existing={b['id']:b for b in (row.bookmarks or [])}
        if len({b.id for b in body.bookmarks})!=len(body.bookmarks):raise HTTPException(422,'书签ID重复')
        row.bookmarks=[b.model_dump()|{'sha256':existing.get(b.id,{}).get('sha256',asset.sha256)} for b in body.bookmarks]
    if body.subtitle_asset_ids is not None:
        refs=[]
        for sid in dict.fromkeys(body.subtitle_asset_ids):
            sub=get_or_404(session,m.Asset,sid)
            if Path(sub.original_name or '').suffix.lower() not in ('.lrc','.srt','.vtt'):raise HTTPException(422,'只支持LRC/SRT/VTT关联')
            if sub.world_id is not None and sub.world_id!=asset.world_id:raise HTTPException(422,'字幕归属不同，请先在素材档案审核世界观')
            refs.append({'id':sub.id,'identity':identity(sub),'sha256':sub.sha256,'title':sub.title})
        row.subtitles=refs
    row.revision=(row.revision or 0)+1;session.commit();return state_dict(session,asset)


@router.get('/tracks/{asset_id}/subtitles/{subtitle_id}')
def subtitle(asset_id:int,subtitle_id:int,session:Session=Depends(get_session)):
    asset=audio_asset(session,asset_id);state=session.get(m.AudioState,asset_id);ref=next((r for r in state.subtitles if r['id']==subtitle_id),None) if state else None
    if ref is None:raise HTTPException(404,'该字幕未关联当前音轨')
    sub=get_or_404(session,m.Asset,subtitle_id)
    if identity(sub)!=ref['identity'] or sub.sha256!=ref['sha256'] or (sub.world_id is not None and sub.world_id!=asset.world_id):raise HTTPException(409,'字幕身份、版本或归属变化，请重新确认')
    path=_file_of(sub)
    if path.stat().st_size>2*1024*1024:raise HTTPException(413,'字幕超过2MiB')
    with path.open('rb') as stream:body=decode_text(stream.read(2*1024*1024))
    try:vtt=subtitles.convert(body,Path(sub.original_name).suffix.lower())
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    return Response(vtt,media_type='text/vtt',headers={'X-Content-Type-Options':'nosniff'})


@router.get('/tracks/{asset_id}/waveform')
def waveform(asset_id:int,session:Session=Depends(get_session)):
    asset=audio_asset(session,asset_id);path=get_settings().thumb_dir/f'audio-wave-{asset.sha256}.json'
    if not path.is_file():return {'available':False,'note':'按需生成，仅支持未压缩PCM WAV'}
    return {'available':True,**json.loads(path.read_text(encoding='utf-8'))}


@router.post('/tracks/{asset_id}/waveform',status_code=202)
def create_waveform(asset_id:int,session:Session=Depends(get_session)):
    asset=audio_asset(session,asset_id);source=_file_of(asset);sha=asset.sha256
    if Path(asset.original_name or '').suffix.lower()!='.wav':raise HTTPException(422,'本轮波形仅支持PCM WAV；压缩音频仍可正常尝试播放')
    def work(job):
        job.check();out=[]
        with wave.open(str(source),'rb') as audio:
            width=audio.getsampwidth();channels=audio.getnchannels();frames=audio.getnframes()
            if width not in (1,2,3,4) or audio.getcomptype()!='NONE':raise ValueError('不是可处理的PCM WAV')
            step=max(1,math.ceil(frames/512));job.total=math.ceil(frames/step)
            # Sample small windows per bin; bounded memory and I/O even for multi-hour PCM.
            for frame in range(0,frames,step):
                job.check();audio.setpos(frame);raw=audio.readframes(min(step,256));peak=0
                for i in range(0,len(raw),width):
                    v=(raw[i]-128)/128 if width==1 else int.from_bytes(raw[i:i+width],'little',signed=True)/(2**(width*8-1));peak=max(peak,abs(v))
                out.append(round(peak,4));job.step('采样PCM波形')
        with new_session() as ses:
            current=audio_asset(ses,asset_id)
            if identity(current)!=identity(asset) or current.sha256!=sha or _file_of(current)!=source:raise ValueError('音轨已变化，停止保存波形')
        path=get_settings().thumb_dir/f'audio-wave-{sha}.json';projectpreview.write_json(path,{'peaks':out,'sampled':True,'note':'每区间采样至多256帧，并非全量峰值分析'});job.result={'asset_id':asset_id,'available':True}
    return jobs.start('audio-waveform','按需PCM波形',0,work).to_dict()
