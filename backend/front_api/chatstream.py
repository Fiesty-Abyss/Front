"""Own the iterator even if ASGI disconnects before its first SSE body event."""
import threading

import anyio
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool


class OwnedIterator:
    def __init__(self, iterator, stop, release):
        self.iterator, self.stop, self.release = iter(iterator), stop, release
        self.lock = threading.RLock()
        self.inflight = self.closed = self.closing = False

    def __iter__(self):
        return self

    def __next__(self):
        with self.lock:
            if self.closing or self.closed:
                raise StopIteration
            self.inflight = True
        try:
            return next(self.iterator)
        finally:
            with self.lock:
                self.inflight = False
                if self.closing:
                    self._finish()

    def _finish(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.iterator.close()
        finally:
            self.release()

    def close(self):
        self.stop.set()
        with self.lock:
            self.closing = True
            if not self.inflight:
                self._finish()
            # A blocked upstream next() still owns its slot until it returns.


class OwnedStreamResponse(StreamingResponse):
    def __init__(self, owner, **kwargs):
        self.owner = owner
        super().__init__(owner, **kwargs)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(self.owner.close)
