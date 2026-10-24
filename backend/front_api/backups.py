"""Private full backups. Never replaces an active database or writes external originals."""
import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from sqlalchemy import create_engine
from . import __version__, jobs
from .config import get_settings
from .db import Base
from .migrate import upgrade

MAX_MANIFEST=32*1024*1024
OWNED=('media','thumbs','project-previews')


def safe_relative(name):
    p=PurePosixPath(name)
    if not name or '\\' in name or ':' in name or p.is_absolute() or any(x in ('..','.') for x in name.split('/')):
        raise ValueError('清单含非法相对路径')
    if p.parts[0] not in (*OWNED,'external','jobs.sqlite3'):
        raise ValueError('清单路径不属于备份数据范围')
    if p.parts[0]=='jobs.sqlite3' and len(p.parts)!=1:raise ValueError('任务账本路径无效')
    reserved={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
    if any(x.endswith((' ','.')) or x.split('.')[0].upper() in reserved or any(ord(c)<32 for c in x) for x in p.parts):raise ValueError('路径含不安全的文件名')
    return p


def checked(root,path):
    path=Path(path)
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):raise ValueError('不跟随数据目录外的链接')
    return path


def digest(path,check=lambda:None):
    h=hashlib.sha256();size=0
    with path.open('rb') as f:
        while block:=f.read(1024*1024):check();h.update(block);size+=len(block)
    return h.hexdigest(),size


def atomic_json(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,path)


def sqlite_copy(source,dest,check=lambda:None):
    with closing(sqlite3.connect(source,timeout=10)) as src,closing(sqlite3.connect(dest)) as dst,src,dst:
        src.backup(dst,pages=256,progress=lambda *args:check())
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite快照完整性检查失败')


def schema_issues(path,complete=False):
    with closing(sqlite3.connect(path)) as db,db:
        names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        allowed=set(Base.metadata.tables)|{'search_index','search_index_content','search_index_data','search_index_idx','search_index_docsize','search_index_config','sqlite_sequence','sqlite_stat1','sqlite_stat4'}
        issues=[f'当前程序不认识数据库表：{x}' for x in names-allowed]
        for name,table in Base.metadata.tables.items():
            if name in names:
                cols={r[1] for r in db.execute(f'PRAGMA table_info("{name}")')}
                issues.extend(f'当前程序不认识字段：{name}.{x}' for x in cols-set(table.columns.keys()))
                if complete:issues.extend(f'迁移后仍缺少字段：{name}.{x}' for x in set(table.columns.keys())-cols)
            elif complete:issues.append(f'迁移后仍缺少数据表：{name}')
        if not {'assets','worlds','characters'}<=names:issues.append('不是可识别的Front数据库')
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':issues.append('数据库完整性检查失败')
        return issues


def inventory(db):
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    managed=set()
    if 'assets' in tables:managed.update(r[0] for r in db.execute('SELECT file_path FROM assets WHERE file_path IS NOT NULL'))
    if 'retained_media' in tables:managed.update(r[0] for r in db.execute('SELECT path FROM retained_media'))
    refs=[]
    if 'external_asset_files' in tables:
        refs.extend({'kind':'asset','id':r[0],'path':r[1],'root':r[2],'sha256':r[3],'included':False} for r in db.execute('SELECT e.asset_id,e.path,e.root,a.sha256 FROM external_asset_files e JOIN assets a ON a.id=e.asset_id'))
    if 'sd_models' in tables:refs.extend({'kind':'sd_model','id':r[0],'path':r[1],'included':False} for r in db.execute('SELECT id,local_path FROM sd_models WHERE local_path IS NOT NULL'))
    if 'live2d_profiles' in tables:refs.extend({'kind':'live2d','id':r[0],'path':r[1],'included':False} for r in db.execute('SELECT id,source_path FROM live2d_profiles'))
    return managed,refs


def put_file(package,source,relative,check):
    safe_relative(relative)
    stat=source.stat();temp=package/('copy-'+uuid.uuid4().hex+'.partial');h=hashlib.sha256();size=0
    try:
        with source.open('rb') as src,temp.open('xb') as dst:
            while block:=src.read(1024*1024):check();dst.write(block);h.update(block);size+=len(block)
        after=source.stat()
        if (stat.st_size,stat.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('备份期间文件发生变化')
        target=package/'objects'/h.hexdigest();target.parent.mkdir(exist_ok=True)
        if target.exists():temp.unlink()
        else:os.replace(temp,target)
        return {'path':relative,'sha256':h.hexdigest(),'size':size}
    finally:temp.unlink(missing_ok=True)


def create(job,external_asset_ids=()):
    settings=get_settings();root=settings.data_dir.resolve();bid=uuid.uuid4().hex
    package=root/'backups'/('full-'+bid);checked(root,package);package.mkdir(parents=True)
    manifest={'format':'front-full-backup','version':1,'front_version':__version__,'id':bid,'created_at':datetime.now(timezone.utc).isoformat(),'status':'building','files':[],'references':[],'issues':[],
              'excluded':['backups','restores','.staging','service logs'],'credentials':'数据库可能包含本机API凭据；备份只保存在本地，不要公开上传'}
    try:
        # Freeze committed metadata while copying owned bytes. jobs.sqlite3 remains separate.
        from .maintenance import freeze
        with freeze(job.check),closing(sqlite3.connect(settings.db_path,timeout=10)) as lock,lock:
            lock.execute('BEGIN IMMEDIATE')
            dbfile=package/'front.db';sqlite_copy(settings.db_path,dbfile,job.check)
            manifest['database']={'sha256':digest(dbfile,job.check)[0],'size':dbfile.stat().st_size}
            with closing(sqlite3.connect(dbfile)) as snapshot,snapshot:expected,refs=inventory(snapshot)
            with closing(sqlite3.connect(dbfile)) as snapshot,snapshot:
                expected_hashes={r[0]:r[1] for r in snapshot.execute('SELECT file_path,sha256 FROM assets WHERE file_path IS NOT NULL AND sha256 IS NOT NULL')}
            manifest['references']=refs
            paths={}
            for folder in OWNED:
                base=root/folder
                if not base.exists():continue
                try:checked(root,base)
                except ValueError:manifest['issues'].append({'path':folder,'status':'link_not_followed'});continue
                for parent,dirs,files in os.walk(base,followlinks=False):
                    job.check()
                    for d in list(dirs):
                        p=Path(parent)/d
                        try:checked(root,p)
                        except ValueError:dirs.remove(d);manifest['issues'].append({'path':str(p.relative_to(root)),'status':'link_not_followed'})
                    for name in files:
                        p=Path(parent)/name;paths[p.relative_to(root).as_posix()]=p
            for rel in expected:
                try:
                    p=safe_relative(rel)
                    if p.parts[0]!='media':raise ValueError('托管原件不在media内')
                    paths.setdefault(rel,root/rel)
                except ValueError:manifest['issues'].append({'path':rel,'status':'invalid_managed_path'})
            for ref in refs:
                p=Path(ref['path']);ref['exists']=p.is_file() if ref['kind']!='live2d' else p.exists()
                if ref['kind']=='asset' and ref['id'] in external_asset_ids:
                    from .projectpreview import stamp
                    with closing(sqlite3.connect(dbfile)) as db,db:
                        old=json.loads(db.execute('SELECT stamp FROM external_asset_files WHERE asset_id=?',(ref['id'],)).fetchone()[0])
                    if not p.is_file() or not p.resolve().is_relative_to(Path(ref['root']).resolve()) or stamp(p)!=old:
                        manifest['issues'].append({'path':ref['path'],'status':'external_changed_or_missing'});continue
                    relative=f'external/{ref["id"]}/{p.name}'
                    if ref.get('sha256'):expected_hashes[relative]=ref['sha256']
                    paths[relative]=p;ref['included']=True;ref['restored_path']=relative
            if set(external_asset_ids)-{r['id'] for r in refs if r['kind']=='asset'}:raise ValueError('选中的外部素材不存在')
            job.total=len(paths)+2
            for relative,path in sorted(paths.items()):
                job.check()
                try:
                    if not relative.startswith('external/'):checked(root,path)
                    entry=put_file(package,path,relative,job.check)
                    manifest['files'].append(entry)
                    expected_sha=expected_hashes.get(relative)
                    if not expected_sha and relative.startswith('media/') and len(path.stem)==64 and all(c in '0123456789abcdef' for c in path.stem):expected_sha=path.stem
                    if expected_sha and entry['sha256']!=expected_sha:manifest['issues'].append({'path':relative,'status':'metadata_hash_mismatch'})
                except (OSError,ValueError) as exc:
                    manifest['issues'].append({'path':relative,'status':'missing' if isinstance(exc,FileNotFoundError) else 'unreadable_or_changed','error_type':type(exc).__name__})
                job.step('备份文件并计算SHA256')
            included={f['path'] for f in manifest['files']}
            for ref in refs:
                if ref.get('included') and ref['restored_path'] not in included:ref['included']=False;ref.pop('restored_path',None)
            if (root/'jobs.sqlite3').exists():
                temp=package/'jobs.snapshot';sqlite_copy(root/'jobs.sqlite3',temp,job.check)
                manifest['files'].append(put_file(package,temp,'jobs.sqlite3',job.check));temp.unlink()
                job.step('任务账本快照已保存')
            lock.rollback()
        manifest['status']='partial' if manifest['issues'] else 'complete'
        atomic_json(package/'manifest.json',manifest)
        job.result={'backup_id':bid,'status':manifest['status'],'files':len(manifest['files'])+1,'issues':len(manifest['issues'])}
        job.step('备份完成；缺失/外部引用已分开记录')
    except BaseException as exc:
        manifest['status']='cancelled' if job.cancel_requested else 'failed'
        manifest['failure_type']=type(exc).__name__;atomic_json(package/'manifest.json',manifest)
        job.result={'backup_id':bid,'status':manifest['status'],'error':str(exc)[:500] if isinstance(exc,ValueError) else '备份未完成；请检查磁盘空间、访问权限或取消状态'};raise


def package_for(bid):
    if len(bid)!=32 or any(c not in '0123456789abcdef' for c in bid):raise ValueError('备份ID无效')
    return get_settings().data_dir/'backups'/('full-'+bid)


def load(package):
    package=Path(package).resolve();path=checked(package,package/'manifest.json')
    if path.stat().st_size>MAX_MANIFEST:raise ValueError('备份清单超过32MiB上限')
    value=json.loads(path.read_text(encoding='utf-8'))
    if value.get('format')!='front-full-backup' or value.get('version')!=1:raise ValueError('不支持的备份格式')
    if value.get('status') not in ('complete','partial'):raise ValueError('备份未完成，不能恢复')
    seen=set()
    for item in value['files']:
        safe_relative(item['path'])
        if item['path'] in seen:raise ValueError('清单含重复路径')
        seen.add(item['path'])
        sha=item['sha256']
        if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('非法SHA256')
    return package,value


def verify(package,check=lambda:None):
    package,manifest=load(package);issues=[]
    db=checked(package,package/'front.db')
    if digest(db,check)!=(manifest['database']['sha256'],manifest['database']['size']):issues.append('数据库Hash不匹配')
    else:issues+=schema_issues(db)
    for item in manifest['files']:
        check()
        try:
            obj=checked(package,package/'objects'/item['sha256'])
            if digest(obj,check)!=(item['sha256'],item['size']):issues.append(f'文件校验失败：{item["path"]}')
        except OSError:issues.append(f'备份对象丢失/无法读取：{item["path"]}')
    return manifest,issues


def restore(job,package,allow_partial=False):
    package=Path(package).resolve();manifest,issues=verify(package,job.check)
    if issues or (manifest['status']=='partial' and not allow_partial):raise ValueError('备份校验失败或含缺失项；不能默认恢复')
    root=get_settings().data_dir/'restores';checked(get_settings().data_dir,root);root.mkdir(exist_ok=True)
    rid=uuid.uuid4().hex;staging=root/(rid+'.partial');target=root/rid;staging.mkdir()
    job.result={'restore_id':rid,'status':'building'};job.total=len(manifest['files'])+2
    try:
        def copy(src,dst):
            dst.parent.mkdir(parents=True,exist_ok=True)
            with src.open('rb') as a,dst.open('xb') as b:
                while block:=a.read(1024*1024):job.check();b.write(block)
        copy(package/'front.db',staging/'front.db')
        if digest(staging/'front.db',job.check)!=(manifest['database']['sha256'],manifest['database']['size']):raise ValueError('恢复数据库Hash不匹配')
        job.step('恢复数据库快照')
        for item in manifest['files']:
            job.check();relative=safe_relative(item['path']);dst=staging/str(relative)
            copy(checked(package,package/'objects'/item['sha256']),dst)
            if digest(dst,job.check)!=(item['sha256'],item['size']):raise ValueError('恢复落盘校验失败')
            job.step('恢复到独立目录并校验')
        # Migrate only the new copy; never changes active engine/session configuration.
        engine=create_engine('sqlite:///'+str(staging/'front.db'))
        try:Base.metadata.create_all(engine);upgrade(engine)
        finally:engine.dispose()
        if schema_issues(staging/'front.db',complete=True):raise ValueError('恢复副本迁移后结构不完整；不能作为已验证数据目录使用')
        from .projectpreview import stamp
        with closing(sqlite3.connect(staging/'front.db')) as db,db:
            for ref in manifest['references']:
                if ref.get('included') and ref['kind']=='asset':
                    p=staging/str(safe_relative(ref['restored_path']))
                    db.execute('UPDATE external_asset_files SET path=?,root=?,stamp=? WHERE asset_id=?',(str(target/ref['restored_path']),str(target),json.dumps(stamp(p)),ref['id']))
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('恢复数据库完整性/关联检查失败')
        report={'status':'verified','backup_id':manifest['id'],'restore_id':rid,'path':str(target),'source_issues':manifest['issues'],'active_data_unchanged':True,'next':'此副本可作为FRONT_DATA_DIR重启使用；当前实例未被替换。'}
        atomic_json(staging/'restore-report.json',report);os.replace(staging,target)
        job.result=report;job.step('独立恢复副本已验证')
    except BaseException as exc:
        atomic_json(staging/'restore-report.json',{'status':'cancelled' if job.cancel_requested else 'failed','failure_type':type(exc).__name__,'active_data_unchanged':True})
        job.result={'restore_id':rid,'status':'failed','error':str(exc)[:500] if isinstance(exc,ValueError) else '恢复未完成；当前数据保持不变，请检查磁盘空间、权限或取消状态'}
        raise
