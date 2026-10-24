"""A shared gate for HTTP mutations, background work and consistent full backups."""
from contextlib import contextmanager
from threading import Condition

_condition=Condition()
_active=0
_frozen=False


def begin():
    global _active
    with _condition:
        if _frozen:return False
        _active+=1;return True


def end():
    global _active
    with _condition:_active-=1;_condition.notify_all()


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
