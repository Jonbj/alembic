"""Persistent asyncio event loop for Celery prefork workers.

asyncio.run() creates and destroys a new event loop on every call. In Celery
prefork workers each task invocation is sequential within a process, so a single
persistent loop per process is safe and avoids repeated setup/teardown overhead.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

_T = TypeVar("_T")
_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
    return _loop


def run_async(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run *coro* on the persistent per-process event loop."""
    return _get_loop().run_until_complete(coro)
