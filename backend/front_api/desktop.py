"""Private loopback sidecar. The desktop shell owns this process and its pipes."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import tempfile
import time

from fastapi.responses import HTMLResponse, JSONResponse


def prepare_folder(folder: Path):
    """Check actual create/write/remove access before opening or migrating the database."""
    try:
        for path in (folder, folder/'logs', folder/'media', folder/'thumbs'):
            path.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=path, prefix='.front-write-check-') as probe:
                probe.write(b'Front'); probe.flush(); os.fsync(probe.fileno())
    except OSError as exc:
        raise RuntimeError('data_directory_unwritable') from exc


@contextlib.contextmanager
def data_lock(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / '.desktop.lock').open('a+b') as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('data_directory_in_use') from exc
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def prepare_data(settings):
    """Reject downgrades; verify a full recoverable package before changing existing schema."""
    if not settings.db_path.is_file():
        return
    from . import backups, jobs, models  # Register all schema without creating the application.
    from .db import Base
    from .migrate import COLUMNS
    import sqlite3
    try:
        issues = backups.schema_issues(settings.db_path)
    except sqlite3.DatabaseError as exc:
        raise RuntimeError('database_incompatible_or_damaged') from exc
    if issues:
        raise RuntimeError('database_incompatible_or_damaged')
    with contextlib.closing(sqlite3.connect(settings.db_path)) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = bool(set(Base.metadata.tables) - tables)
        for table, column, _ in COLUMNS:
            if table in tables and column not in {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}:
                missing = True
    if missing:
        job = jobs.Job('full-backup', '桌面升级前完整备份')
        backups.create(job)
        package = backups.package_for(job.result['backup_id'])
        manifest, issues = backups.verify(package)
        if issues or manifest['status'] != 'complete':
            raise RuntimeError('upgrade_backup_incomplete')
        # Does not switch or replace the active database. Its isolated migration must pass first.
        backups.restore(jobs.Job('full-restore', '桌面升级前隔离恢复验证'), package)


BOOTSTRAP = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="referrer" content="no-referrer"><title>Front 正在连接</title>
<body style="background:#17141f;color:#e7def5;font:16px system-ui;padding:3rem">
<p id="status">正在连接本机 Front…</p>
<script nonce="NONCE">
const token=location.hash.slice(1);history.replaceState(null,'','/_desktop/bootstrap');
fetch('/_desktop/session',{method:'POST',headers:{Authorization:'Bearer '+token}})
.then(r=>{if(!r.ok)throw Error();location.replace('/')})
.catch(()=>document.getElementById('status').textContent='无法连接本机服务，请关闭窗口后重试。');
</script></body></html>"""


def protect(app, *, token: str, port: int, stop):
    origin = f'http://127.0.0.1:{port}'
    cookie = f'front_desktop_{port}'
    session_secret = secrets.token_urlsafe(32)
    @app.middleware('http')
    async def desktop_guard(request, call_next):
        if request.headers.get('host') != f'127.0.0.1:{port}':
            return JSONResponse({'detail': 'Invalid local host'}, status_code=403)
        supplied_origin = request.headers.get('origin')
        if supplied_origin and supplied_origin != origin:
            return JSONResponse({'detail': 'Foreign origin denied'}, status_code=403)
        path = request.url.path
        bearer = request.headers.get('authorization', '')
        authenticated = secrets.compare_digest(bearer.encode('utf-8'), ('Bearer '+token).encode('utf-8'))
        if path == '/_desktop/bootstrap' and request.method == 'GET':
            nonce = secrets.token_urlsafe(18)
            return HTMLResponse(BOOTSTRAP.replace('NONCE', nonce), headers={
                'Content-Security-Policy': f"default-src 'none'; script-src 'nonce-{nonce}'; connect-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'",
                'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
        if path == '/_desktop/session' and request.method == 'POST':
            if not authenticated:
                return JSONResponse({'detail':'Unauthorized'},status_code=401)
            response = JSONResponse({'ok':True}, headers={'Cache-Control':'no-store'})
            response.set_cookie(cookie, session_secret, httponly=True, samesite='strict', path='/')
            return response
        if not authenticated and not secrets.compare_digest(request.cookies.get(cookie, '').encode('utf-8'), session_secret.encode('utf-8')):
            return JSONResponse({'detail':'Unauthorized'},status_code=401)
        if path == '/_desktop/shutdown' and request.method == 'POST':
            if not authenticated:
                return JSONResponse({'detail':'Shell authorization required'},status_code=403)
            stop()
            return JSONResponse({'ok':True})
        response = await call_next(request)
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response


def serve(folder: Path):
    prepare_folder(folder)
    os.environ['FRONT_DATA_DIR'] = str(folder.resolve())
    from .config import get_settings
    get_settings.cache_clear()
    settings = get_settings()
    with data_lock(folder):
        logs = folder/'logs'; logs.mkdir(exist_ok=True)
        # Lifecycle log only; arbitrary HTTP/provider exception bodies and access URLs are not persisted.
        logging.getLogger().handlers = [logging.NullHandler()]
        for name in ('uvicorn','uvicorn.error','uvicorn.access'):
            logging.getLogger(name).handlers=[logging.NullHandler()]
            logging.getLogger(name).propagate=False
        logger=logging.getLogger('front.desktop');logger.propagate=False;logger.setLevel(logging.INFO)
        handler=RotatingFileHandler(logs/'desktop.log',maxBytes=1024*1024,backupCount=3,encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
        logger.info('Preparing local data')
        try:
            prepare_data(settings)
            from .main import create_app
            import uvicorn
            app=create_app(settings)
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
                listener.bind(('127.0.0.1',0));listener.listen(128)
                port=listener.getsockname()[1]
                token=secrets.token_urlsafe(32)
                server=uvicorn.Server(uvicorn.Config(app,log_config=None,access_log=False,workers=1))
                protect(app,token=token,port=port,stop=lambda:setattr(server,'should_exit',True))
                async def runner():
                    async def ready():
                        while not server.started:
                            await asyncio.sleep(.02)
                        logger.info('Local service ready')
                        print(json.dumps({'port':port,'token':token,'pid':os.getpid()}),flush=True)
                    waiter=asyncio.create_task(ready())
                    try:await server.serve(sockets=[listener])
                    finally:waiter.cancel()
                asyncio.run(runner())
            logger.info('Local service stopped')
        except Exception as exc:
            logger.error('Sidecar failed: %s',type(exc).__name__)
            raise
        finally:
            handler.close();logger.removeHandler(handler)


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',required=True)
    args=parser.parse_args()
    try:
        serve(Path(args.data_dir))
    except Exception as exc:
        # Only stable codes cross the shell pipe; never raw paths, tokens or provider exceptions.
        known={'data_directory_in_use','data_directory_unwritable','database_incompatible_or_damaged','upgrade_backup_incomplete'}
        code=str(exc) if str(exc) in known else 'sidecar_initialization_failed'
        print(json.dumps({'error':code}),flush=True)
        raise SystemExit(1)


if __name__=='__main__':
    main()
