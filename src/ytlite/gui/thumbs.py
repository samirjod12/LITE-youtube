"""Lazy thumbnail loading: disk cache -> network (HTTPS only, async, no threads)."""
from __future__ import annotations

from collections import OrderedDict, deque
from typing import Callable

from PySide6.QtCore import QObject, Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

MAX_THUMB_BYTES = 1_500_000
TIMEOUT_MS = 10_000


class ThumbLoader(QObject):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.nam = QNetworkAccessManager(self)
        self._queue: deque[str] = deque()
        self._active: dict[QNetworkReply, str] = {}
        self._waiting: dict[str, list[Callable]] = {}
        self._mem: OrderedDict[str, QPixmap] = OrderedDict()

    # -- public ------------------------------------------------------------
    def request(self, url: str, callback: Callable[[QPixmap | None], None]) -> None:
        if not url.startswith("https://"):
            callback(None)
            return
        pm = self._mem.get(url)
        if pm is not None:
            self._mem.move_to_end(url)
            callback(pm)
            return
        data = self.ctx.thumb_cache.read(url)
        if data:
            pm = self._decode(data)
            if pm is not None:
                self._remember(url, pm)
                callback(pm)
                return
        if self.ctx.blocker.check_url(url):
            callback(None)
            return
        waiters = self._waiting.setdefault(url, [])
        waiters.append(callback)
        if len(waiters) == 1:
            self._queue.append(url)
            self._pump()

    def cancel_pending(self) -> None:
        """Drop queued downloads and abort running ones (called on page change)."""
        self._queue.clear()
        active_urls = set(self._active.values())
        for url in [u for u in self._waiting if u not in active_urls]:
            del self._waiting[url]
        for reply in list(self._active):
            reply.abort()

    def clear_memory(self) -> None:
        self._mem.clear()

    # -- internals ---------------------------------------------------------
    def _remember(self, url: str, pm: QPixmap) -> None:
        cap = self.ctx.settings.profile.mem_thumbs
        if cap <= 0:
            return
        self._mem[url] = pm
        self._mem.move_to_end(url)
        while len(self._mem) > cap:
            self._mem.popitem(last=False)

    def _decode(self, data: bytes) -> QPixmap | None:
        prof = self.ctx.settings.profile
        pm = QPixmap()
        if not pm.loadFromData(data):
            return None
        mode = (Qt.TransformationMode.SmoothTransformation if prof.smooth_thumbs
                else Qt.TransformationMode.FastTransformation)
        pm = pm.scaled(prof.thumb_w, prof.thumb_h,
                       Qt.AspectRatioMode.KeepAspectRatioByExpanding, mode)
        if pm.width() > prof.thumb_w or pm.height() > prof.thumb_h:
            x = (pm.width() - prof.thumb_w) // 2
            y = (pm.height() - prof.thumb_h) // 2
            pm = pm.copy(x, y, prof.thumb_w, prof.thumb_h)
        return pm

    def _pump(self) -> None:
        limit = max(1, self.ctx.settings.profile.thumb_threads)
        while self._queue and len(self._active) < limit:
            url = self._queue.popleft()
            req = QNetworkRequest(QUrl(url))
            req.setTransferTimeout(TIMEOUT_MS)
            req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
            reply = self.nam.get(req)
            self._active[reply] = url
            reply.finished.connect(lambda r=reply: self._finished(r))

    def _finished(self, reply: QNetworkReply) -> None:
        url = self._active.pop(reply, None)
        callbacks = self._waiting.pop(url, []) if url else []
        pm = None
        if url and reply.error() == QNetworkReply.NetworkError.NoError:
            data = bytes(reply.readAll())
            if 0 < len(data) <= MAX_THUMB_BYTES:
                pm = self._decode(data)
                if pm is not None:
                    self.ctx.thumb_cache.write(url, data)
                    self._remember(url, pm)
        reply.deleteLater()
        for cb in callbacks:
            cb(pm)
        self._pump()
