"""Read-only project inventory. Reports contain private paths; stay in local data."""
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from . import models as m
from .config import get_settings
from .filetypes import IMAGE_EXT, TEXT_EXT, KIND_BY_EXT
from .ingest import decode_text


def stamp(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_dev, stat.st_ino]


def candidate(relative, kind):
    low = relative.lower()
    if any(word in low for word in ('角色','人物','主角','character')):
        return 'character', '文件或目录名称含人物相关词；尚未确认'
    for words, category in [(('门派','组织','宗门','organization'),'organization'),(('地点','地理','location'),'location'),(('剧情','小说','novel','story'),'novel'),(('世界观','world'),'world')]:
        if any(word in low for word in words):
            return category, '依据文件或目录名称建议；尚未确认'
    return ('image' if kind == 'drawing' else 'resource'), '依据格式建议；尚未确认'


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)


def build(root, files, unsupported, session, job, world_id):
    folder = get_settings().data_dir / 'project-previews'
    cache_path = folder / 'fingerprints' / (hashlib.sha256(str(root).encode()).hexdigest() + '.json')
    try:
        cache = json.loads(cache_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        cache = {}
    if not isinstance(cache,dict):
        cache = {}
    report = {'root':str(root),'world_id':world_id,'created_at':datetime.now(timezone.utc).isoformat(),
              'files':[], 'unsupported':unsupported,'total':len(files),'bytes':0,'reused_hashes':0,'errors':0,'duplicate_files':0}
    new_cache, seen = {}, {}
    job.total = len(files)
    job.result = {'processed':0,'total':len(files),'report_id':None}
    for index, path in enumerate(files):
        job.check()
        relative = path.relative_to(root).as_posix()
        item = {'index':index,'relative':relative,'name':path.name,'kind':'other','duplicate_of':None,'existing':[]}
        try:
            if path.is_dir():
                item.update(kind='bundle',candidate='resource',reason='关联模型文件夹；请使用模型专用扫描',note='本阶段不展开或复制关联包')
            else:
                before = stamp(path)
                item.update(bytes=before[0],mtime=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(),stamp=before)
                ext = path.suffix.lower()
                item['kind'] = 'drawing' if ext in IMAGE_EXT else 'novel' if ext in TEXT_EXT else KIND_BY_EXT.get(ext,'other')
                item['candidate'], item['reason'] = candidate(relative,item['kind'])
                old = cache.get(relative) or {}
                if not isinstance(old,dict):
                    old = {}
                old_hash = old.get('sha256')
                valid_hash = isinstance(old_hash,str) and len(old_hash) == 64 and all(c in '0123456789abcdef' for c in old_hash)
                if old.get('stamp') == before and valid_hash:
                    digest = old['sha256']; report['reused_hashes'] += 1
                else:
                    hasher = hashlib.sha256()
                    with path.open('rb') as handle:
                        while chunk := handle.read(1024 * 1024):
                            job.check(); hasher.update(chunk)
                    digest = hasher.hexdigest()
                if stamp(path) != before:
                    raise ValueError('扫描时文件变化，请重新预览')
                item['sha256'] = digest
                new_cache[relative] = {'stamp':before,'sha256':digest}
                item['duplicate_of'] = seen.get(digest)
                seen.setdefault(digest,index)
                matches = session.execute(select(m.Asset.id,m.Asset.world_id).where(m.Asset.sha256 == digest).limit(20)).all()
                item['existing'] = [{'asset_id':aid,'same_world':wid == world_id and world_id is not None} for aid,wid in matches]
                if item['duplicate_of'] is not None or matches:
                    report['duplicate_files'] += 1
                if ext in IMAGE_EXT:
                    try:
                        with Image.open(path) as image:
                            item.update(width=image.width,height=image.height)
                    except (OSError, ValueError, Image.DecompressionBombError):
                        item['note'] = '图片头无法识别；未解码完整图片'
                report['bytes'] += before[0]
        except (OSError, ValueError) as exc:
            item['error'] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            report['errors'] += 1
        report['files'].append(item)
        job.result['processed'] = index + 1
        job.step(relative)
    job.check()
    write_json(folder / f'{job.id}.json',report)
    # Cache is advisory for preview only, never trusted as import/overwrite authorization.
    try:
        write_json(cache_path,new_cache)
    except OSError:
        job.errors.append('指纹缓存无法写入；本次预览报告已保存，下次重新计算哈希')
    job.result = {k:report[k] for k in ('total','bytes','errors','duplicate_files','reused_hashes','unsupported')}
    job.result['report_id'] = job.id


def load(report_id):
    if len(report_id) != 12 or any(c not in '0123456789abcdef' for c in report_id):
        raise ValueError('预览报告不存在')
    try:
        return json.loads((get_settings().data_dir / 'project-previews' / f'{report_id}.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):
        raise ValueError('预览报告不存在或已清理') from None


def file_of(report, index):
    if not 0 <= index < len(report['files']):
        raise ValueError('文件不存在')
    item = report['files'][index]
    root = Path(report['root']).resolve()
    path = (root / item['relative']).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
        raise ValueError('原文件已移动、失效或不支持文件预览')
    if item.get('stamp') != stamp(path):
        raise ValueError('原文件已变化，请重新扫描预览')
    return item,path


def text_preview(path):
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return {'text':'','note':'仅在点击显示时加载这一张原图；不批量解码整个项目'}
    if ext in TEXT_EXT or ext in ('.py','.json','.yaml','.yml','.js','.ts'):
        with path.open('rb') as handle:
            raw = handle.read(65536)
        return {'text':decode_text(raw,truncated=path.stat().st_size > len(raw))[:4000],'note':'只读片段，最多读取64KiB并展示4000字符；脚本不执行'}
    if ext == '.docx':
        import zipfile
        from .filetypes import analyze
        with zipfile.ZipFile(path) as archive:
            if sum(i.file_size for i in archive.infolist() if i.filename.endswith('.xml')) > 8 * 1024 * 1024:
                return {'text':'','note':'DOCX XML超过8MiB，本阶段仅显示元数据'}
        data = analyze(path,path.name)
        return {'text':(data.content or '')[:4000],'note':'DOCX只读文本片段，非完整排版或全文承诺'}
    return {'text':'','note':'本阶段该格式仅显示元数据；不执行文件或打开外部软件'}
