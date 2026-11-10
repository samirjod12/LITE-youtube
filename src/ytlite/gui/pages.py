"""Main content pages: Home, Search, Trending, Subscriptions, History, Watch Later,
Playlists and the Player page (launcher with quality selector)."""
from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QMessageBox, QPushButton, QSlider,
                               QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from ..formats import fmt_duration, fmt_views, pick_default
from ..search import ExtractResult, VideoItem
from .widgets import Pager, VideoGrid

TREND_TOPICS = ("Music", "Gaming", "News", "Sports", "Science and technology", "Movie trailers",
                "Cooking", "Documentary")


def _label(text="", name=None, wrap=False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


# ---------------------------------------------------------------------------------
class ResultsView(QWidget):
    """Status line + grid + pager + background fetching with caching."""

    def __init__(self, win, empty_text: str):
        super().__init__()
        self.win, self.ctx = win, win.ctx
        self.source: dict | None = None
        self.page = 1
        self._seq = 0
        self._task = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.status = _label(empty_text, "Secondary", wrap=True)
        self.status.setContentsMargins(12, 8, 12, 4)
        self.grid = VideoGrid(self.ctx, win.thumbs)
        self.pager = Pager()
        lay.addWidget(self.status)
        lay.addWidget(self.grid, 1)
        lay.addWidget(self.pager)
        self.pager.pageRequested.connect(self._goto)

    def load(self, source: dict, page: int = 1) -> None:
        self.source, self.page = source, page
        self._fetch()

    def _goto(self, page: int) -> None:
        if page >= 1 and self.source:
            self.page = page
            self._fetch()

    def _fetch(self) -> None:
        prof = self.ctx.settings.profile
        src, page = dict(self.source), self.page
        key = json.dumps([src, page, prof.results], sort_keys=True)
        cached = self.ctx.meta_cache.get(key, prof.meta_ttl_s)
        if cached is not None:
            self._show([VideoItem.from_dict(d) for d in cached])
            return
        if self._task is not None:
            self._task.cancelled = True            # superseded request does no work if still queued
        self._seq += 1
        seq = self._seq
        self.status.setObjectName("Secondary")
        self.status.setText("Searching... (slow connections can take several seconds)")
        self.pager.update_state(page, False, busy=True)
        svc, size, w = self.ctx.search, prof.results, prof.thumb_w
        kind = src["t"]

        def work():
            if kind == "video":
                return svc.search_videos(src["q"], page, size, w)
            if kind == "channel":
                return svc.search_channels(src["q"], page, size, w)
            return svc.channel_videos(src["url"], page, size, w)

        self._task = self.win.runner.submit(
            work, on_done=lambda items: self._done(seq, key, items),
            on_fail=lambda k, m: self._fail(seq, k, m))

    def _done(self, seq: int, key: str, items: list) -> None:
        if seq != self._seq:
            return
        self.ctx.meta_cache.put(key, [i.to_dict() for i in items])
        self._show(items)

    def _show(self, items: list[VideoItem]) -> None:
        prof = self.ctx.settings.profile
        self.grid.set_items(items)
        self.pager.update_state(self.page, len(items) >= prof.results)
        self.status.setObjectName("Secondary")
        self.status.setStyleSheet("")
        title = self.source.get("name") if self.source and self.source["t"] == "chvideos" else ""
        if not items:
            self.status.setText("No results." if self.page == 1 else "No more results.")
        else:
            prefix = f"Channel: {title} · " if title else ""
            self.status.setText(f"{prefix}{len(items)} results · page {self.page}")

    def _fail(self, seq: int, kind: str, message: str) -> None:
        if seq != self._seq:
            return
        self.grid.clear()
        self.pager.update_state(self.page, False)
        self.status.setText("⚠ " + message)
        self.status.setStyleSheet("color: #E5604F;")
        self.win.notify(message)


# ---------------------------------------------------------------------------------
class HomePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.ctx = win, win.ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 0)
        lay.addWidget(_label("Home", "Heading"))
        self.hint = _label("", "Secondary", wrap=True)
        lay.addWidget(self.hint)
        chips = QHBoxLayout()
        for topic in TREND_TOPICS:
            b = QToolButton()
            b.setObjectName("Chip")
            b.setText(topic)
            b.clicked.connect(lambda _c=False, t=topic: win.open_topic(t))
            chips.addWidget(b)
        chips.addStretch(1)
        lay.addLayout(chips)
        lay.addWidget(_label("Recently played", "Secondary"))
        self.grid = VideoGrid(self.ctx, win.thumbs)
        lay.addWidget(self.grid, 1)

    def refresh(self):
        s = self.ctx.settings
        rows = self.ctx.db(self.ctx.storage.history, s.profile.results, 0, default=[]) or []
        self.grid.set_items([VideoItem.from_dict(r) for r in rows])
        notes = ["Search above, or click a topic below to browse videos."]
        if self.ctx.mpv_exe() is None:
            notes.append("⚠ mpv.exe was not found: playback will not work until it is placed in the "
                         "'mpv' folder (see README).")
        if not rows:
            notes.append("Videos you play will appear here (stored only on this computer).")
        self.hint.setText("\n".join(notes))


class SearchPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(_label("Search", "Heading"))
        bar.addStretch(1)
        bar.addWidget(_label("Look for:", "Secondary"))
        self.mode = QComboBox()
        self.mode.addItem("Videos", "video")
        self.mode.addItem("Channels", "channel")
        bar.addWidget(self.mode)
        bar.setContentsMargins(0, 0, 12, 0)
        lay.addLayout(bar)
        self.results = ResultsView(win, "Type a search above and press Enter.")
        lay.addWidget(self.results, 1)
        self.grid = self.results.grid

    def search(self, query: str) -> None:
        self.results.load({"t": self.mode.currentData(), "q": query}, 1)

    def open_channel(self, item: VideoItem) -> None:
        self.results.load({"t": "chvideos", "url": item.channel_url or item.url, "name": item.title}, 1)


class TrendingPage(QWidget):
    def __init__(self, win):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 0, 0)
        lay.addWidget(_label("Trending", "Heading"))
        lay.addWidget(_label("YouTube's own Trending feed is not available through yt-dlp, so these "
                             "buttons simply run a normal search for a popular topic. Nothing is "
                             "loaded until you click.", "Secondary", wrap=True))
        chips = QHBoxLayout()
        for topic in TREND_TOPICS:
            b = QToolButton()
            b.setObjectName("Chip")
            b.setText(topic)
            b.clicked.connect(lambda _c=False, t=topic: self.results.load({"t": "video", "q": t}, 1))
            chips.addWidget(b)
        chips.addStretch(1)
        lay.addLayout(chips)
        self.results = ResultsView(win, "Choose a topic.")
        lay.addWidget(self.results, 1)
        self.grid = self.results.grid


class SubscriptionsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.ctx = win, win.ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 0, 0)
        lay.addWidget(_label("Subscriptions", "Heading"))
        lay.addWidget(_label("YouTube Lite never signs in, so your YouTube subscriptions are not "
                             "available. Instead, save channels locally: search with “Channels”, or "
                             "use ⋯ → “Save channel” on any video. Click a channel to see its latest "
                             "videos.", "Secondary", wrap=True))
        self.grid = VideoGrid(self.ctx, win.thumbs)
        lay.addWidget(self.grid, 1)

    def refresh(self):
        rows = self.ctx.db(self.ctx.storage.channels, default=[]) or []
        self.grid.set_items([VideoItem.from_dict(r) for r in rows])


class LibraryPage(QWidget):
    """History / Watch Later: DB-backed, paginated, with Clear all."""

    def __init__(self, win, kind: str, title: str):
        super().__init__()
        self.win, self.ctx, self.kind = win, win.ctx, kind
        self.page = 1
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(_label(title, "Heading"))
        bar.addStretch(1)
        self.clear_btn = QPushButton("Clear all")
        self.clear_btn.setObjectName("Danger")
        self.clear_btn.clicked.connect(self._clear)
        bar.addWidget(self.clear_btn)
        bar.setContentsMargins(0, 0, 12, 0)
        lay.addLayout(bar)
        self.status = _label("", "Secondary")
        lay.addWidget(self.status)
        self.grid = VideoGrid(self.ctx, win.thumbs)
        self.pager = Pager()
        lay.addWidget(self.grid, 1)
        lay.addWidget(self.pager)
        self.pager.pageRequested.connect(self._goto)

    def _goto(self, page):
        self.page = max(1, page)
        self.refresh()

    def refresh(self):
        st, size = self.ctx.storage, self.ctx.settings.profile.results
        off = (self.page - 1) * size
        if self.kind == "history":
            rows = self.ctx.db(st.history, size, off, default=[]) or []
            total = self.ctx.db(st.history_count, default=0) or 0
        else:
            rows = self.ctx.db(st.watch_later, size, off, default=[]) or []
            total = self.ctx.db(st.watch_later_count, default=0) or 0
        if not rows and self.page > 1:
            self.page -= 1
            return self.refresh()
        self.grid.set_items([VideoItem.from_dict(r) for r in rows])
        self.status.setText(f"{total} saved" if total else "Nothing here yet.")
        self.pager.update_state(self.page, off + len(rows) < total)

    def _clear(self):
        if QMessageBox.question(self, "Clear all", "Remove every entry in this list?") \
                == QMessageBox.StandardButton.Yes:
            fn = self.ctx.storage.clear_history if self.kind == "history" else self.ctx.storage.clear_watch_later
            self.ctx.db(fn)
            self.page = 1
            self.refresh()


class PlaylistsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.ctx = win, win.ctx
        self.page = 1
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 0, 0)
        lay.addWidget(_label("Playlists", "Heading"))
        bar = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setMinimumWidth(220)
        self.combo.currentIndexChanged.connect(lambda _i: self._select())
        self.new_btn = QPushButton("New")
        self.ren_btn = QPushButton("Rename")
        self.del_btn = QPushButton("Delete")
        self.del_btn.setObjectName("Danger")
        for w in (self.combo, self.new_btn, self.ren_btn, self.del_btn):
            bar.addWidget(w)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.status = _label("", "Secondary")
        lay.addWidget(self.status)
        self.grid = VideoGrid(self.ctx, win.thumbs)
        self.pager = Pager()
        lay.addWidget(self.grid, 1)
        lay.addWidget(self.pager)
        self.new_btn.clicked.connect(self._new)
        self.ren_btn.clicked.connect(self._rename)
        self.del_btn.clicked.connect(self._delete)
        self.pager.pageRequested.connect(lambda p: self._goto(p))

    @property
    def current_id(self) -> int | None:
        return self.combo.currentData()

    def refresh(self, keep: int | None = None):
        keep = keep if keep is not None else self.current_id
        lists = self.ctx.db(self.ctx.storage.playlists, default=[]) or []
        self.combo.blockSignals(True)
        self.combo.clear()
        for p in lists:
            self.combo.addItem(f"{p['name']} ({p['count']})", p["id"])
        idx = self.combo.findData(keep) if keep is not None else -1
        self.combo.setCurrentIndex(idx if idx >= 0 else (0 if lists else -1))
        self.combo.blockSignals(False)
        for b in (self.ren_btn, self.del_btn):
            b.setEnabled(bool(lists))
        self._select()

    def _select(self):
        self.page = 1
        self._load()

    def _goto(self, page):
        self.page = max(1, page)
        self._load()

    def _load(self):
        pid = self.current_id
        if pid is None:
            self.grid.clear()
            self.status.setText("No playlists yet. Click New, or use ⋯ → “Add to playlist” on a video.")
            self.pager.update_state(1, False)
            return
        size = self.ctx.settings.profile.results
        off = (self.page - 1) * size
        rows = self.ctx.db(self.ctx.storage.playlist_items, pid, size, off, default=[]) or []
        total = self.ctx.db(self.ctx.storage.playlist_count, pid, default=0) or 0
        self.grid.set_items([VideoItem.from_dict(r) for r in rows])
        self.status.setText(f"{total} videos" if total else "This playlist is empty.")
        self.pager.update_state(self.page, off + len(rows) < total)

    def _new(self):
        name, ok = QInputDialog.getText(self, "New playlist", "Name:")
        if ok and name.strip():
            pid = self.ctx.db(self.ctx.storage.create_playlist, name)
            if pid is not None:
                self.refresh(keep=pid)

    def _rename(self):
        pid = self.current_id
        if pid is None:
            return
        name, ok = QInputDialog.getText(self, "Rename playlist", "New name:")
        if ok and name.strip():
            self.ctx.db(self.ctx.storage.rename_playlist, pid, name)
            self.refresh(keep=pid)

    def _delete(self):
        pid = self.current_id
        if pid is not None and QMessageBox.question(
                self, "Delete playlist", "Delete this playlist? The videos themselves are not affected.") \
                == QMessageBox.StandardButton.Yes:
            self.ctx.db(self.ctx.storage.delete_playlist, pid)
            self.refresh(keep=-1)


# ---------------------------------------------------------------------------------
class PlayerPage(QWidget):
    """Player launcher: extraction, quality selector, live mpv status and controls."""

    COLS = ("Quality", "Codec", "FPS", "Bitrate", "Audio", "Note")

    def __init__(self, win):
        super().__init__()
        self.win, self.ctx = win, win.ctx
        self.ctrl = win.player
        self.item: VideoItem | None = None
        self.result: ExtractResult | None = None
        self._seq = 0
        self._logged = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 8)
        lay.setSpacing(6)
        self.title = _label("No video selected", "Heading", wrap=True)
        self.meta = _label("", "Secondary", wrap=True)
        self.status = _label("", None, wrap=True)
        self.live = _label("", "Secondary", wrap=True)
        self.advice = _label("", "Warn", wrap=True)
        self.desc = _label("", "Secondary", wrap=True)
        for w in (self.title, self.meta, self.status, self.live, self.advice, self.desc):
            lay.addWidget(w)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(len(self.COLS) - 1, QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(190)
        self.table.cellDoubleClicked.connect(lambda *_: self.open_selected())
        lay.addWidget(self.table)
        lay.addWidget(_label(
            "Available resolution is not the same as smooth playback. 360p/480p are the safe choices "
            "on this laptop; 720p H.264 is the main high-quality target; 1080p is experimental. "
            "“Bitrate (reported)” comes from YouTube's metadata, not a measurement; the live line "
            "above shows what mpv actually measures.", "Secondary", wrap=True))

        row = QHBoxLayout()
        self.open_btn = QPushButton("Open player")
        self.open_btn.setObjectName("Primary")
        self.stop_btn = QPushButton("Stop")
        self.back_btn = QPushButton("Return to application")
        self.web_btn = QPushButton("Open in browser (Web Mode)")
        for b in (self.open_btn, self.stop_btn, self.back_btn, self.web_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        ctl = QHBoxLayout()
        self.pause_btn = QToolButton(); self.pause_btn.setText("⏯ Pause/Play")
        self.back10 = QToolButton(); self.back10.setText("−10 s")
        self.fwd10 = QToolButton(); self.fwd10.setText("+10 s")
        self.fs_btn = QToolButton(); self.fs_btn.setText("Fullscreen")
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(self.ctx.settings["volume"])
        self.vol.setFixedWidth(110)
        self.speed = QComboBox()
        for sp in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            self.speed.addItem(f"{sp:g}×", sp)
        self.speed.setCurrentIndex(max(0, self.speed.findData(self.ctx.settings["speed"])))
        for w in (self.pause_btn, self.back10, self.fwd10, self.fs_btn):
            ctl.addWidget(w)
        ctl.addWidget(_label("Volume", "Secondary"))
        ctl.addWidget(self.vol)
        ctl.addWidget(_label("Speed", "Secondary"))
        ctl.addWidget(self.speed)
        ctl.addStretch(1)
        lay.addLayout(ctl)
        lay.addStretch(1)

        self.open_btn.clicked.connect(self.open_selected)
        self.stop_btn.clicked.connect(self.ctrl.stop)
        self.back_btn.clicked.connect(win.return_to_app)
        self.web_btn.clicked.connect(lambda: self.item and win.open_web(self.item))
        self.pause_btn.clicked.connect(lambda: self.ctrl.command("cycle", "pause"))
        self.back10.clicked.connect(lambda: self.ctrl.command("seek", -10, "relative"))
        self.fwd10.clicked.connect(lambda: self.ctrl.command("seek", 10, "relative"))
        self.fs_btn.clicked.connect(lambda: self.ctrl.command("cycle", "fullscreen"))
        self.vol.valueChanged.connect(lambda v: self.ctrl.command("set_property", "volume", v))
        self.speed.currentIndexChanged.connect(
            lambda _i: self.ctrl.command("set_property", "speed", self.speed.currentData()))
        self.ctrl.stateChanged.connect(self._on_state)
        self.ctrl.statsUpdated.connect(self._on_stats)
        self._set_enabled(False)

    # -- helpers -----------------------------------------------------------
    def _set_status(self, text: str, level: str = ""):
        self.status.setText(text)
        color = {"error": "#E5604F", "ok": "#4FBF7F", "warn": "#E5A028"}.get(level, "#A0A8B5")
        self.status.setStyleSheet(f"color: {color};")

    def _set_enabled(self, have_streams: bool):
        self.open_btn.setEnabled(have_streams)
        self.web_btn.setEnabled(self.item is not None)

    def selected_option(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if rows and self.result:
            return self.result.options[rows[0].row()]
        return None

    # -- flow --------------------------------------------------------------
    def start(self, item: VideoItem) -> None:
        if self.ctrl.is_running():
            self.ctrl.stop()
        self.item = item
        self._logged = False
        self.title.setText(item.title)
        self.meta.setText(" · ".join(x for x in (item.channel, fmt_duration(item.duration),
                                                  fmt_views(item.views)) if x))
        self.advice.clear()
        self.live.clear()
        self.desc.clear()
        self.table.setRowCount(0)
        self._set_enabled(False)
        if self.result and self.result.video_id == item.id and self.result.fresh():
            self._on_extracted(self._seq, self.result)       # reuse recent extraction
            return
        self.result = None
        self._seq += 1
        seq = self._seq
        self._set_status("Reading stream information (nothing is downloaded)...")
        s = self.ctx.settings
        pref, cap = s["codec_preference"], s["audio_cap_kbps"]
        self.win.runner.submit(
            lambda: self.ctx.search.extract_streams(item.id, pref, cap),
            on_done=lambda r: self._on_extracted(seq, r),
            on_fail=lambda k, m: self._on_extract_failed(seq, k, m))

    def _on_extract_failed(self, seq, kind, message):
        if seq != self._seq:
            return
        self._set_status("⚠ " + message, "error")
        self.win.notify(message)

    def _on_extracted(self, seq, result: ExtractResult):
        if seq != self._seq and result is not self.result:
            return
        self.result = result
        if result.title:
            self.title.setText(result.title)
        meta = [result.channel or (self.item.channel if self.item else ""),
                fmt_duration(result.duration), fmt_views(result.views), result.pretty_date()]
        self.meta.setText(" · ".join(x for x in meta if x))
        if self.ctx.settings.profile.rich_metadata and result.description:
            self.desc.setText(result.description[:500])
        self.table.setRowCount(len(result.options))
        for r, o in enumerate(result.options):
            audio = ("in stream" if not o.audio_url and not o.note.startswith("No separate")
                     else (f"{o.audio_codec or 'audio'}" + (f" ~{o.audio_kbps:.0f} kbps" if o.audio_kbps else "")))
            cells = (o.title, o.codec_label, o.fps_label, o.bitrate_label, audio, o.note)
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                it.setToolTip(text)
                self.table.setItem(r, c, it)
        default = pick_default(result.options, self.ctx.settings.effective_quality())
        if default is not None:
            self.table.selectRow(result.options.index(default))
        self._set_enabled(True)
        if self.ctx.settings["auto_play"] and default is not None:
            self.open_selected()
        else:
            self._set_status("Choose a quality, then press “Open player”.")

    def open_selected(self) -> None:
        opt, item = self.selected_option(), self.item
        if opt is None or item is None:
            return
        if self.ctx.blocker.check_url(opt.video_url) or (opt.audio_url and self.ctx.blocker.check_url(opt.audio_url)):
            self._set_status("⚠ The ad blocker refused this stream host. Add it to the allowlist or "
                             "switch the blocker off.", "error")
            return
        resume = self.ctrl.last_pos if (self.ctrl.video_id == item.id and self.ctrl.is_running()) else 0.0
        if self.ctx.settings["save_watch_history"] and not self._logged and self.ctx.storage.available:
            self.ctx.db(self.ctx.storage.add_history, item.to_dict())
            self._logged = True
        self.advice.clear()
        self.ctrl.launch(item.id, opt, self.result.title if self.result else item.title, resume)

    # -- player events -----------------------------------------------------
    def _on_state(self, state: str, message: str):
        if state == "launching":
            self._set_status(message)
        elif state == "playing":
            o = self.ctrl.option
            self._set_status(f"Playing {o.title} · {o.codec_label}" if o else "Playing", "ok")
        elif state == "stopped":
            self._set_status("Stopped. mpv has been closed.")
            self.live.clear()
        elif state == "error":
            self._set_status("⚠ " + message, "error")
            self.win.notify("Playback problem: " + message.splitlines()[0])

    def _on_stats(self, sample: dict, rep):
        def t(v):
            return fmt_duration(v) if isinstance(v, (int, float)) else "?"
        parts = [f"{t(sample.get('time-pos'))} / {t(sample.get('duration'))}"]
        w, h = sample.get("width"), sample.get("height")
        if w and h:
            parts.append(f"{w}×{h}")
        if sample.get("video-codec"):
            parts.append(str(sample["video-codec"]).split(" ")[0])
        parts.append(f"decoding: {rep.decode}")
        drop = f"dropped frames: {rep.dropped}"
        if rep.drop_percent is not None:
            drop += f" ({rep.drop_percent}%)"
        parts.append(drop)
        br = sample.get("video-bitrate")
        if isinstance(br, (int, float)) and br > 0:
            parts.append(f"video bitrate: {br / 1000:.0f} kbps (measured)")
        if sample.get("paused-for-cache"):
            parts.append("buffering…")
        self.live.setText(" · ".join(parts) + "   [values measured by mpv]")
        if rep.advice:
            self.advice.setText("⚠ " + rep.advice)
