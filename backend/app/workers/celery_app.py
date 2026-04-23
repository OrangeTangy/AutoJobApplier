"""
In-process task queue shim — drop-in replacement for Celery in desktop mode.

Provides a `celery` object with a `.task()` decorator that returns a callable
with a `.delay()` method. Tasks run in a shared `ThreadPoolExecutor` rather
than in remote Celery workers, and can be scheduled periodically via
`register_periodic()`.

The public decorator signature matches the subset of Celery we use
(`@celery.task(name=..., bind=..., max_retries=..., queue=...)`) so existing
task definitions in `app.workers.tasks` keep working unchanged.
"""
from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

import structlog

from app.config import get_settings

settings = get_settings()
logger = structlog.get_logger(__name__)


@dataclass
class _TaskMeta:
    name: str
    bind: bool = False
    max_retries: int = 0
    queue: str = "default"
    retries: int = 0


@dataclass
class _Retry(Exception):
    exc: BaseException | None = None
    countdown: int = 0


class _BoundTaskContext:
    """Mimics the `self` argument Celery passes to `bind=True` tasks."""

    def __init__(self, meta: _TaskMeta):
        self._meta = meta

    @property
    def request(self):  # pragma: no cover — not used internally
        return self

    @property
    def retries(self) -> int:
        return self._meta.retries

    def retry(self, exc: BaseException | None = None, countdown: int = 0):
        raise _Retry(exc=exc, countdown=countdown)


class _Task:
    """Wraps a callable so it can be invoked synchronously or via `.delay()`."""

    def __init__(self, fn: Callable[..., Any], meta: _TaskMeta, executor: ThreadPoolExecutor):
        self._fn = fn
        self._meta = meta
        self._executor = executor

    # Direct call — preserves the original function signature
    def __call__(self, *args, **kwargs):
        if self._meta.bind:
            return self._fn(_BoundTaskContext(self._meta), *args, **kwargs)
        return self._fn(*args, **kwargs)

    def delay(self, *args, **kwargs):
        """Submit this task for background execution."""
        return self._executor.submit(self._run_with_retry, args, kwargs)

    apply_async = delay  # alias for Celery compatibility

    def _run_with_retry(self, args, kwargs):
        meta = _TaskMeta(
            name=self._meta.name,
            bind=self._meta.bind,
            max_retries=self._meta.max_retries,
            queue=self._meta.queue,
        )
        while True:
            try:
                if meta.bind:
                    return self._fn(_BoundTaskContext(meta), *args, **kwargs)
                return self._fn(*args, **kwargs)
            except _Retry as r:
                if meta.retries >= meta.max_retries:
                    logger.error(
                        "task_retry_exhausted",
                        task=meta.name,
                        retries=meta.retries,
                        error=str(r.exc),
                    )
                    return None
                meta.retries += 1
                logger.warning(
                    "task_retry",
                    task=meta.name,
                    attempt=meta.retries,
                    countdown=r.countdown,
                )
                if r.countdown > 0:
                    time.sleep(min(r.countdown, 30))  # cap local retry delay
            except Exception as exc:
                logger.error("task_failed", task=meta.name, error=str(exc))
                return None


class _InProcessCelery:
    """Minimal Celery stand-in exposing only the decorator surface we use."""

    def __init__(self):
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, settings.worker_threads),
            thread_name_prefix="autojob-task",
        )
        self._tasks: dict[str, _Task] = {}
        self._periodic: list[tuple[int, _Task, tuple, dict]] = []
        self._periodic_stop = threading.Event()
        self._periodic_thread: threading.Thread | None = None

    def task(
        self,
        *args,
        name: str | None = None,
        bind: bool = False,
        max_retries: int = 0,
        queue: str = "default",
        **_: Any,
    ):
        """Decorator compatible with `@celery.task(name=..., bind=..., ...)`."""

        def wrap(fn: Callable[..., Any]) -> _Task:
            meta = _TaskMeta(
                name=name or f"{fn.__module__}.{fn.__name__}",
                bind=bind,
                max_retries=max_retries,
                queue=queue,
            )
            task = _Task(fn, meta, self._executor)
            self._tasks[meta.name] = task
            return task

        # Support both `@celery.task` and `@celery.task(...)`
        if args and callable(args[0]) and not name:
            fn = args[0]
            return wrap(fn)
        return wrap

    def register_periodic(
        self,
        task: _Task,
        interval_seconds: int,
        args: tuple = (),
        kwargs: dict | None = None,
    ) -> None:
        """Run `task.delay(*args, **kwargs)` every `interval_seconds`."""
        self._periodic.append((interval_seconds, task, args, kwargs or {}))

    def start_scheduler(self) -> None:
        """Launch a daemon thread that fires registered periodic tasks."""
        if not settings.scheduler_enabled or self._periodic_thread:
            return

        def _loop():
            tick = 0
            while not self._periodic_stop.is_set():
                for interval, task, args, kwargs in self._periodic:
                    if tick > 0 and tick % interval == 0:
                        try:
                            task.delay(*args, **kwargs)
                        except Exception as exc:  # pragma: no cover
                            logger.error(
                                "periodic_fire_failed",
                                task=task._meta.name,
                                error=str(exc),
                            )
                self._periodic_stop.wait(1)
                tick += 1

        self._periodic_thread = threading.Thread(
            target=_loop, name="autojob-scheduler", daemon=True
        )
        self._periodic_thread.start()

    def shutdown(self) -> None:
        self._periodic_stop.set()
        self._executor.shutdown(wait=False, cancel_futures=True)


# Async→sync bridge shared by `tasks.py` — safe for thread-pool execution.
def run_coro_blocking(coro):
    """Execute an async coroutine from within a worker thread.

    Each worker thread gets its own event loop on first use, avoiding the
    `RuntimeError: There is no current event loop` that the default
    `asyncio.get_event_loop()` raises on threads.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError("loop is already running")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


celery = _InProcessCelery()
