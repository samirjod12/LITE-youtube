"""Background tasks. A single shared pool with ONE thread keeps network work
serialised ("one active search request") and the thread count minimal."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..errors import from_exception


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str, str)      # kind, user message


class Task(QRunnable):
    def __init__(self, fn: Callable, *args):
        super().__init__()
        self.fn = fn
        self.args = args
        self.cancelled = False
        self.signals = _Signals()

    def run(self):
        if self.cancelled:           # superseded before it started: do no network work
            return
        try:
            result = self.fn(*self.args)
        except Exception as exc:     # never let a worker exception escape
            err = from_exception(exc)
            self.signals.failed.emit(err.kind, err.message)
            return
        self.signals.done.emit(result)


class TaskRunner(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.pool.setExpiryTimeout(2000)      # idle worker thread exits after 2 s
        self._live: set[Task] = set()

    def submit(self, fn: Callable, args: tuple = (), on_done: Callable | None = None,
               on_fail: Callable | None = None) -> Task:
        task = Task(fn, *args)
        self._live.add(task)

        def finish(*_args):
            self._live.discard(task)

        if on_done:
            task.signals.done.connect(on_done)
        if on_fail:
            task.signals.failed.connect(on_fail)
        task.signals.done.connect(finish)
        task.signals.failed.connect(lambda *_: finish())
        self.pool.start(task)
        return task

    def shutdown(self):
        self.pool.clear()
        for t in list(self._live):
            t.cancelled = True
        self.pool.waitForDone(1500)
