"""Reusable widgets: video card, scrolling grid (cards are reused, never recreated),
and a small pager."""
from __future__ import annotations

from functools import partial

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)

from ..formats import fmt_duration, fmt_views
from ..search import VideoItem


class VideoCard(QFrame):
    activated = Signal(object)                 # VideoItem
    menuRequested = Signal(object, QPoint)     # VideoItem, global position

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.item: VideoItem | None = None
        self.thumb_requested = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        self.thumb = QLabel()
        self.thumb.setObjectName("Thumb")
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge = QLabel(self.thumb)
        self.badge.setObjectName("Badge")
        self.badge.hide()
        self.title = QLabel()
        self.title.setObjectName("CardTitle")
        self.title.setWordWrap(True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.channel = QLabel()
        self.channel.setObjectName("Secondary")
        self.meta = QLabel()
        self.meta.setObjectName("Secondary")
        self.more = QToolButton()
        self.more.setText("⋯")
        self.more.setToolTip("More actions")
        self.more.clicked.connect(self._on_more)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.meta, 1)
        row.addWidget(self.more, 0)
        lay.addWidget(self.thumb)
        lay.addWidget(self.title)
        lay.addWidget(self.channel)
        lay.addLayout(row)

    def apply_profile(self, thumb_w: int, thumb_h: int) -> None:
        self.thumb.setFixedSize(thumb_w, thumb_h)
        self.setFixedWidth(thumb_w + 18)
        self.title.setFixedHeight(self.title.fontMetrics().lineSpacing() * 2 + 2)
        self.title.setFixedWidth(thumb_w)

    def set_item(self, item: VideoItem | None, show_duration=True, show_views=True) -> None:
        self.item = item
        self.thumb_requested = False
        self.thumb.clear()                      # release the pixmap
        if item is None:
            self.title.clear()
            self.channel.clear()
            self.meta.clear()
            self.badge.hide()
            return
        self.title.setText(item.title)
        self.title.setToolTip(item.title)
        fm = self.channel.fontMetrics()
        width = max(40, self.thumb.width() - 4)
        self.channel.setText(fm.elidedText(item.channel, Qt.TextElideMode.ElideRight, width))
        self.channel.setToolTip(item.channel)
        if item.kind == "channel":
            subs = fmt_views(item.views).replace("views", "subscribers") if item.views else ""
            self.meta.setText(("Channel" + (f" · {subs}" if subs else "")))
            self.badge.hide()
            self.thumb.setText("Channel")
            return
        self.meta.setText(fmt_views(item.views) if show_views else "")
        dur = fmt_duration(item.duration)
        if dur and show_duration:
            self.badge.setText(dur)
            self.badge.adjustSize()
            self.badge.move(self.thumb.width() - self.badge.width() - 4,
                            self.thumb.height() - self.badge.height() - 4)
            self.badge.show()
        else:
            self.badge.hide()

    def set_pixmap(self, pm) -> None:
        self.thumb.setPixmap(pm)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.item is not None:
            self.activated.emit(self.item)
        elif ev.button() == Qt.MouseButton.RightButton and self.item is not None:
            self.menuRequested.emit(self.item, ev.globalPosition().toPoint())
        super().mousePressEvent(ev)

    def _on_more(self):
        if self.item is not None:
            self.menuRequested.emit(self.item, self.more.mapToGlobal(QPoint(0, self.more.height())))


class VideoGrid(QScrollArea):
    activated = Signal(object)
    menuRequested = Signal(object, QPoint)

    def __init__(self, ctx, loader, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.loader = loader
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setSpacing(8)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setWidget(self.body)
        self.cards: list[VideoCard] = []
        self.items: list[VideoItem] = []
        self._cols = 0
        # Debounce timer: only runs briefly after a scroll/resize, never polls.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self.load_visible)
        self.verticalScrollBar().valueChanged.connect(lambda _v: self._timer.start())

    # -- content -----------------------------------------------------------
    def _ensure_cards(self, n: int) -> None:
        while len(self.cards) < n:
            card = VideoCard(self.body)
            card.activated.connect(self.activated)
            card.menuRequested.connect(self.menuRequested)
            card.hide()
            self.cards.append(card)

    def set_items(self, items: list[VideoItem]) -> None:
        self.loader.cancel_pending()
        self.items = list(items)
        prof = self.ctx.settings.profile
        s = self.ctx.settings
        self._ensure_cards(len(items))
        for i, card in enumerate(self.cards):
            if i < len(items):
                card.apply_profile(prof.thumb_w, prof.thumb_h)
                card.set_item(items[i], s["show_duration"], s["show_views"])
                card.show()
            else:
                card.set_item(None)
                card.hide()
        self._relayout(force=True)
        self.verticalScrollBar().setValue(0)
        self._timer.start()

    def clear(self) -> None:
        self.set_items([])

    def refresh_profile(self) -> None:
        """Profile (thumbnail size) changed: re-render the current page."""
        self.loader.clear_memory()
        self.set_items(self.items)

    # -- layout ------------------------------------------------------------
    def _relayout(self, force: bool = False) -> None:
        prof = self.ctx.settings.profile
        card_w = prof.thumb_w + 18
        cols = max(1, (self.viewport().width() - 8) // (card_w + 8))
        if cols == self._cols and not force:
            return
        self._cols = cols
        while self.grid.count():
            self.grid.takeAt(0)
        for idx, card in enumerate(self.cards[:len(self.items)]):
            self.grid.addWidget(card, idx // cols, idx % cols)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._relayout()
        self._timer.start()

    # -- lazy thumbnails ---------------------------------------------------
    def load_visible(self) -> None:
        view = self.viewport().rect().adjusted(0, -120, 0, 120)
        for card in self.cards[:len(self.items)]:
            item = card.item
            if item is None or card.thumb_requested or not item.thumb_url:
                continue
            top_left = card.mapTo(self.viewport(), QPoint(0, 0))
            if QRect(top_left, card.size()).intersects(view):
                card.thumb_requested = True
                self.loader.request(item.thumb_url, partial(self._on_thumb, card, item.id))

    @staticmethod
    def _on_thumb(card: VideoCard, item_id: str, pixmap) -> None:
        if pixmap is not None and card.item is not None and card.item.id == item_id:
            card.set_pixmap(pixmap)


class Pager(QWidget):
    pageRequested = Signal(int)
    MAX_PAGE = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.page = 1
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        self.prev = QPushButton("‹ Previous")
        self.next = QPushButton("Next ›")
        self.label = QLabel("Page 1")
        self.label.setObjectName("Secondary")
        lay.addStretch(1)
        lay.addWidget(self.prev)
        lay.addWidget(self.label)
        lay.addWidget(self.next)
        lay.addStretch(1)
        self.prev.clicked.connect(lambda: self.pageRequested.emit(self.page - 1))
        self.next.clicked.connect(lambda: self.pageRequested.emit(self.page + 1))
        self.update_state(1, False)

    def update_state(self, page: int, has_more: bool, busy: bool = False) -> None:
        self.page = page
        self.label.setText(f"Page {page}")
        self.prev.setEnabled(page > 1 and not busy)
        self.next.setEnabled(has_more and page < self.MAX_PAGE and not busy)
        self.setVisible(page > 1 or has_more)
