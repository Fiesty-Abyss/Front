"""A shared gate for HTTP mutations, background work and consistent full backups."""
from contextlib import contextmanager
from threading import Condition
import secrets

_condition=Condition()
_active=0
_frozen=False
_reservations=set()


class MutationGate:
    """ASGI scope covers streaming bodies and their final database writes, not just headers."""
    def __init__(self, app):self.app=app
    async def __call__(self, scope, receive, send):
        path=scope.get('path','')
        mutation=scope['type']=='http' and path.startswith('/api/') and scope.get('method') in ('POST','PUT','PATCH','DELETE')
        if path.startswith('/api/jobs/') and path.endswith('/cancel'):mutation=False
        if not mutation:return await self.app(scope,receive,send)
        if not begin():
            from fastapi.responses import JSONResponse
            response=JSONResponse({'detail':'正在备份或准备更新，资料写入暂缓；请稍后重试。'},status_code=423)
            return await response(scope,receive,send)
        try:await self.app(scope,receive,send)
        finally:end()


def begin():
    global _active
    with _condition:
        if _frozen or _reservations:return False
        _active+=1;return True


def end():
    global _active
    with _condition:_active-=1;_condition.notify_all()


def reserve_writes():
    """Only reserve an idle writer gate; full-backup freeze remains permitted."""
    with _condition:
        if _frozen or _active or _reservations:
            raise RuntimeError('writers_busy')
        token=secrets.token_urlsafe(24)
        _reservations.add(token)
        return token


def release_writes(token):
    with _condition:
        _reservations.discard(token)
        _condition.notify_all()


@contextmanager
def operation(check):
    while not begin():
        check()
        with _condition:_condition.wait(.1)
    try:check();yield
    finally:end()


@contextmanager
def freeze(check):
    global _frozen
    with _condition:
        while _frozen or _active:
            check();_condition.wait(.1)
        check();_frozen=True
    try:yield
    finally:
        with _condition:_frozen=False;_condition.notify_all()
