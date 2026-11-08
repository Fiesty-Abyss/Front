"""Explicit, bounded metadata lookup. No model loading, cover fetching or entity creation."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from . import civitai, jobs, matching
from .config import get_settings
from .galgame import sources

client_factory = lambda: httpx.Client(timeout=httpx.Timeout(12, connect=5), follow_redirects=False)
MAX_RESPONSE = 2 * 1024 * 1024
TTL = 3600
_locks = {name: threading.Lock() for name in ('openlibrary', *sources.SOURCES, 'civitai')}
_last = {}
_cache_lock = threading.RLock()


class MetadataProvider(Protocol):
    name: str
    kinds: tuple[str, ...]

    def search(self, query: dict, token: str | None) -> list[dict]: ...
    def detail(self, sid: str, kind: str, token: str | None) -> dict | None: ...


def text(value, limit=200):
    return value[:limit].strip() if isinstance(value, str) else None


def strings(value, limit=30):
    return list(dict.fromkeys(text(v) for v in value[:limit] if text(v))) if isinstance(value, list) else []


def url(value):
    if not isinstance(value, str) or len(value) > 1000:
        return None
    p = urlsplit(value)
    return value if p.scheme == 'https' and p.hostname and not p.username and not p.password else None


def normalized(raw, provider, kind):
    if not isinstance(raw, dict) or not isinstance(raw.get('sid'), (str, int)):
        raise ValueError('invalid metadata record')
    result = {k: text(raw.get(k), 6000 if k == 'description' else 500 if k in ('trigger_words',) else 200)
              for k in ('title', 'title_cn', 'original', 'description', 'publisher', 'developer', 'date', 'base_model', 'version', 'trigger_words', 'model_type', 'version_id')}
    result.update(provider=provider, source=provider, sid=str(raw['sid'])[:80], kind=kind,
                  url=url(raw.get('url')), aliases=strings(raw.get('aliases')), tags=strings(raw.get('tags')),
                  authors=strings(raw.get('authors')), platforms=strings(raw.get('platforms')),
                  covers=[u for u in (url(v) for v in raw.get('covers', [])[:4]) if u],
                  year=raw.get('year') if type(raw.get('year')) is int and 0 < raw['year'] <= 9999 else None)
    if not result['title']:
        raise ValueError('missing title')
    return result


def _json(path, params=None):
    with client_factory() as client:
        with client.stream('GET', 'https://openlibrary.org' + path, params=params,
                           headers={'User-Agent': sources.USER_AGENT, 'Accept': 'application/json'}) as response:
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = bytearray()
            for block in response.iter_bytes(16384):
                if len(data) + len(block) > MAX_RESPONSE:
                    raise ValueError('metadata response too large')
                data.extend(block)
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError('metadata response is not an object')
            return result


class OpenLibrary:
    name, kinds = 'openlibrary', ('book',)

    def search(self, query, token=None):
        params = {'title': query['title'], 'limit': 10,
                  'fields': 'key,title,author_name,first_publish_year,cover_i'}
        if query.get('author'):
            params['author'] = query['author']
        raw = _json('/search.json', params) or {}
        docs = raw.get('docs')
        if not isinstance(docs, list):
            raise ValueError('missing docs')
        out = []
        for item in docs[:10]:
            if not isinstance(item, dict) or not re.fullmatch(r'/works/OL\d+W', str(item.get('key', ''))):
                continue
            covers = [f"https://covers.openlibrary.org/b/id/{item['cover_i']}-L.jpg?default=false"] if type(item.get('cover_i')) is int and item['cover_i'] > 0 else []
            out.append({'sid': item['key'].split('/')[-1], 'title': item.get('title'), 'authors': item.get('author_name'),
                        'year': item.get('first_publish_year'), 'url': 'https://openlibrary.org' + item['key'], 'covers': covers})
        return out

    def detail(self, sid, kind, token=None):
        if not re.fullmatch(r'OL\d+W', sid):
            raise ValueError('invalid Open Library work id')
        raw = _json(f'/works/{sid}.json')
        if raw is None:
            return None
        description = raw.get('description')
        if isinstance(description, dict):
            description = description.get('value')
        # Work-level dates/publishers/ISBNs are not edition facts; never invent them.
        return {'sid': sid, 'title': raw.get('title'), 'description': description,
                'aliases': raw.get('other_titles'), 'tags': raw.get('subjects'),
                'url': f'https://openlibrary.org/works/{sid}',
                'covers': [f'https://covers.openlibrary.org/b/id/{i}-L.jpg?default=false' for i in (raw.get('covers') or [])[:4] if type(i) is int and i > 0]}


class GameProvider:
    def __init__(self, name):
        self.name, self.kinds = name, ('game',)

    def search(self, query, token=None):
        return sources.search(self.name, query['title'], token)[:10]

    def detail(self, sid, kind, token=None):
        if not re.fullmatch(r'v?\d{1,18}', sid):
            raise ValueError('invalid game id')
        item = sources.detail(self.name, sid, token, False)
        if item:
            item = {**item, 'covers': [item['cover']] if item.get('cover') else []}
        return item


class CivitaiProvider:
    name, kinds = 'civitai', ('model',)

    def search(self, query, token=None):
        if not re.fullmatch(r'[a-fA-F0-9]{64}', query['title']):
            raise ValueError('Civitai requires SHA256')
        item = self.detail(query['title'], 'model')
        return [item] if item else []

    def detail(self, sid, kind, token=None):
        if not re.fullmatch(r'[a-fA-F0-9]{64}', sid):
            raise ValueError('Civitai requires SHA256')
        raw = civitai.lookup(sid)
        if raw is None:
            return None
        summary = civitai.summarize(raw)
        hashes = [str((f.get('hashes') or {}).get('SHA256', '')).lower() for f in raw.get('files', []) if isinstance(f, dict)]
        if any(hashes) and sid.lower() not in hashes:
            raise ValueError('source hash mismatch')
        return {'sid': sid.lower(), 'title': summary['model_name'], 'version': summary['version_name'],
                'base_model': summary['base_model'], 'trigger_words': ', '.join(summary['trained_words']),
                'url': summary['url'], 'covers': summary['image_urls'], 'model_type': summary['type'],
                'version_id': str(summary['version_id']) if summary['version_id'] else None}


PROVIDERS: dict[str, MetadataProvider] = {p.name: p for p in (OpenLibrary(), *(GameProvider(n) for n in sources.SOURCES), CivitaiProvider())}


def capabilities():
    return [{'id': p.name, 'kinds': p.kinds, 'search': True, 'detail': True, 'cover_candidates': True,
             'aliases': p.name != 'civitai', 'tags': p.name != 'civitai', 'provenance': True,
             'refresh': True, 'automatic_refresh': False, 'enabled': enabled() and (sources.enabled() if p.name in sources.SOURCES else get_settings().civitai_enabled if p.name == 'civitai' else True)} for p in PROVIDERS.values()]


def enabled():
    return os.environ.get('FRONT_METADATA', 'on').lower() not in ('off', '0', 'false', 'no')


def cache_dir():
    directory = get_settings().data_dir / 'metadata-cache'
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _cached(key):
    path = cache_dir() / f'{key}.json'
    with _cache_lock:
        try:
            if time.time() - path.stat().st_mtime > TTL or path.stat().st_size > 128 * 1024:
                return None
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None


def _save(key, result):
    with _cache_lock:
        _save_locked(key, result)


def _save_locked(key, result):
    directory = cache_dir()
    temporary = directory / f'{uuid.uuid4().hex}.tmp'
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    temporary.replace(directory / f'{key}.json')
    # Advisory cache, never the authoritative provenance. Bound disk use independently of history.
    for path in sorted(directory.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[128:]:
        path.unlink(missing_ok=True)


def receipt(value):
    if not re.fullmatch(r'[a-f0-9]{32}', value):
        raise HTTPException(422, '无效的资料预览凭据')
    result = _cached(value)
    if not result or result.get('receipt') != value:
        raise HTTPException(410, '资料预览已过期，请重新读取详情')
    return result


def run(job, operation, query, cfg):
    results, errors = {}, {}
    for name in query['providers']:
        job.check()
        provider = PROVIDERS[name]
        cache_key = hashlib.sha256(json.dumps([operation, query, name, hashlib.sha256((cfg.get('bangumi_token') or '').encode()).hexdigest()], sort_keys=True).encode()).hexdigest()
        cached = _cached(cache_key)
        try:
            lock = _locks[name]
            while not lock.acquire(timeout=.1):
                job.check()
            try:
                # Recheck inside the per-source gate to coalesce concurrent human requests.
                cached = _cached(cache_key)
                if cached and operation == 'detail' and not _cached(cached['receipt']):
                    cached = None
                if cached:
                    output = cached
                else:
                    while time.monotonic() - _last.get(name, 0) < 1.1:
                        job.check()
                        time.sleep(.05)
                    _last[name] = time.monotonic()
                    if operation == 'search':
                        raw = provider.search(query, cfg.get('bangumi_token'))
                        items = matching.rank(query['title'], [normalized(i, name, query['kind']) for i in raw[:10]], query.get('author'), query.get('year'))
                        if query['kind'] == 'model':
                            for item in items:
                                item['match'] = {'tier': 'exact', 'score': 1.0, 'requires_confirmation': True, 'reasons': ['按 SHA256 查得的版本；来源声明不等于引擎兼容验证']}
                        output = {'items': items}
                    else:
                        raw = provider.detail(query['sid'], query['kind'], cfg.get('bangumi_token'))
                        if not raw:
                            raise ValueError('not found')
                        item = normalized(raw, name, query['kind'])
                        # Preserve bounded search evidence (e.g. author/year) absent from work detail.
                        output = {'item': item, 'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'receipt': uuid.uuid4().hex}
                        _save(output['receipt'], output)
                    _save(cache_key, output)
            finally:
                lock.release()
            job.check()
            results[name] = output
        except jobs.Cancelled:
            raise
        except (httpx.HTTPError, sources.SourceError, civitai.CivitaiDisabled, ValueError, TypeError, KeyError, AttributeError):
            errors[name] = '来源不可用、限流或返回格式异常；请稍后重试。未修改本地资料。'
        job.result = {'results': results.copy(), 'errors': errors.copy(), 'operation': operation}
        job.step()
    job.result = {'results': results, 'errors': errors, 'operation': operation}
    if not results:
        raise RuntimeError('所有所选来源均未返回可用资料；本地资料未修改')
