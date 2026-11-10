"""Settings: General, Performance, Playback, Ad blocker, Storage, Appearance, About."""
from __future__ import annotations

import platform
import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from .. import __version__, hwinfo
from ..cache import dir_size
from ..config import PROFILES, QUALITY_CHOICES
from ..procmem import process_memory
from ..search import ytdlp_version


def _note(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("Secondary")
    lab.setWordWrap(True)
    return lab


def _tab(*widgets_or_layouts) -> QWidget:
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    for w in widgets_or_layouts:
        (lay.addLayout if hasattr(w, "addWidget") and not isinstance(w, QWidget) else lay.addWidget)(w)
    lay.addStretch(1)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(page)
    return scroll


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):.1f} MB"


class SettingsPage(QWidget):
    TAB_NAMES = ("General", "Performance", "Playback", "Ad blocker", "Storage", "Appearance", "About")

    def __init__(self, win):
        super().__init__()
        self.win, self.ctx = win, win.ctx
        self.s = self.ctx.settings
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 8)
        head = QLabel("Settings")
        head.setObjectName("Heading")
        lay.addWidget(head)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.tabs.addTab(self._general(), "General")
        self.tabs.addTab(self._performance(), "Performance")
        self.tabs.addTab(self._playback(), "Playback")
        self.tabs.addTab(self._adblock(), "Ad blocker")
        self.tabs.addTab(self._storage(), "Storage")
        self.tabs.addTab(self._appearance(), "Appearance")
        self.tabs.addTab(self._about(), "About")
        self.tabs.currentChanged.connect(lambda _i: self.refresh())

    def show_tab(self, name: str):
        self.tabs.setCurrentIndex(self.TAB_NAMES.index(name))

    def refresh(self):
        self._refresh_storage()
        self._refresh_adblock()
        self._refresh_about()

    # -- helpers -----------------------------------------------------------
    def _commit(self):
        self.ctx.save_settings()

    def _check(self, text, key, after=None, sub=None) -> QCheckBox:
        box = QCheckBox(text)
        store = self.s[sub] if sub else self.s.data
        box.setChecked(bool(store[key]))

        def changed(state):
            store[key] = bool(state)
            self._commit()
            if after:
                after()
        box.toggled.connect(changed)
        return box

    # -- General -----------------------------------------------------------
    def _general(self):
        reset = QPushButton("Reset all settings to defaults")
        reset.clicked.connect(self._reset)
        return _tab(
            self._check("Remember my searches (local only)", "save_search_history"),
            self._check("Remember what I play (Recently played)", "save_watch_history"),
            self._check("Start playback automatically after the stream is read", "auto_play"),
            self._check("Warn me before opening Web Mode (browser)", "confirm_web_mode"),
            _note("YouTube Lite has no account, no telemetry and never asks for a Google password. "
                  "Everything is stored in this program's own folder."),
            reset)

    def _reset(self):
        if QMessageBox.question(self, "Reset", "Reset all settings to defaults?") \
                == QMessageBox.StandardButton.Yes:
            self.s.reset()
            self.ctx.blocker.enabled = False
            self._commit()
            self.win.apply_settings()
            QMessageBox.information(self, "Reset", "Settings were reset. Reopen this page to see them.")

    # -- Performance -------------------------------------------------------
    def _performance(self):
        self.profile_combo = QComboBox()
        for key, p in PROFILES.items():
            self.profile_combo.addItem(p.label, key)
        self.profile_combo.setCurrentIndex(self.profile_combo.findData(self.s["profile"]))
        self.profile_desc = _note("")
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        self._show_profile_desc()
        return _tab(QLabel("Performance mode (changes apply immediately, no restart):"),
                    self.profile_combo, self.profile_desc,
                    _note("ECO is the default and is recommended for 2 GB of RAM. Idle memory "
                          "depends on your system: see the About page to measure it."))

    def _show_profile_desc(self):
        p = PROFILES[self.profile_combo.currentData()]
        self.profile_desc.setText(
            f"{p.description}\nResults/page: {p.results} · thumbnails {p.thumb_w}×{p.thumb_h} · "
            f"default quality {p.default_quality}p · thumbnails kept in RAM beyond the visible "
            f"page: {p.mem_thumbs} · cache limit ×{p.cache_mult:g}")

    def _profile_changed(self):
        self.s["profile"] = self.profile_combo.currentData()
        self._show_profile_desc()
        self._commit()
        self.win.apply_settings()

    def sync_profile_combo(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.setCurrentIndex(self.profile_combo.findData(self.s["profile"]))
        self.profile_combo.blockSignals(False)
        self._show_profile_desc()

    # -- Playback ----------------------------------------------------------
    def _playback(self):
        form = QFormLayout()
        self.q_combo = QComboBox()
        self.q_combo.addItem("Use the performance mode's default", 0)
        for q in QUALITY_CHOICES:
            self.q_combo.addItem({720: "720p HD", 1080: "1080p Full HD (experimental)"}.get(q, f"{q}p"), q)
        self.q_combo.setCurrentIndex(self.q_combo.findData(self.s["default_quality"]))
        self.q_combo.currentIndexChanged.connect(lambda _i: self._set("default_quality", self.q_combo.currentData()))

        self.hw_combo = QComboBox()
        self.hw_combo.addItem("Automatic (recommended)", "auto")
        self.hw_combo.addItem("Automatic, copy-back (more compatible)", "auto-copy")
        self.hw_combo.addItem("Software only", "no")
        self.hw_combo.setCurrentIndex(self.hw_combo.findData(self.s["hwdec"]))
        self.hw_combo.currentIndexChanged.connect(lambda _i: self._set("hwdec", self.hw_combo.currentData()))

        self.codec_combo = QComboBox()
        self.codec_combo.addItem("Prefer H.264 (recommended)", "h264")
        self.codec_combo.addItem("Any codec (best bitrate)", "any")
        self.codec_combo.setCurrentIndex(self.codec_combo.findData(self.s["codec_preference"]))
        self.codec_combo.currentIndexChanged.connect(lambda _i: self._set("codec_preference", self.codec_combo.currentData()))

        self.speed_combo = QComboBox()
        for sp in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            self.speed_combo.addItem(f"{sp:g}×", sp)
        self.speed_combo.setCurrentIndex(max(0, self.speed_combo.findData(self.s["speed"])))
        self.speed_combo.currentIndexChanged.connect(lambda _i: self._set("speed", self.speed_combo.currentData()))

        self.vol_spin = QSpinBox()
        self.vol_spin.setRange(0, 100)
        self.vol_spin.setValue(self.s["volume"])
        self.vol_spin.valueChanged.connect(lambda v: self._set("volume", v))
        self.audio_spin = QSpinBox()
        self.audio_spin.setRange(48, 320)
        self.audio_spin.setSuffix(" kbps")
        self.audio_spin.setValue(self.s["audio_cap_kbps"])
        self.audio_spin.valueChanged.connect(lambda v: self._set("audio_cap_kbps", v))
        self.thr_spin = QSpinBox()
        self.thr_spin.setRange(0, 8)
        self.thr_spin.setSpecialValueText("mpv decides")
        self.thr_spin.setValue(self.s["decoder_threads"])
        self.thr_spin.valueChanged.connect(lambda v: self._set("decoder_threads", v))

        for label, w in (("Default quality", self.q_combo), ("Hardware decoding", self.hw_combo),
                         ("Codec preference", self.codec_combo), ("Start speed", self.speed_combo),
                         ("Start volume", self.vol_spin), ("Audio bitrate cap", self.audio_spin),
                         ("Decoder threads", self.thr_spin)):
            form.addRow(label, w)
        holder = QWidget()
        holder.setLayout(form)

        preset = QPushButton("Apply Intel Celeron 847 compatibility profile")
        preset.clicked.connect(self._apply_preset)
        detect = QPushButton("Detect hardware")
        detect.clicked.connect(self._detect)
        self.hw_text = QTextEdit()
        self.hw_text.setReadOnly(True)
        self.hw_text.setFixedHeight(120)
        self.hw_text.setPlaceholderText("Press “Detect hardware” to see CPU, RAM, GPU and driver.")
        row = QHBoxLayout()
        row.addWidget(preset)
        row.addWidget(detect)
        row.addStretch(1)
        rowc = QWidget()
        rowc.setLayout(row)
        return _tab(
            holder,
            self._check("Fast software decode assist (skips some filtering; slightly lower quality)",
                        "sw_assist"),
            self._check("Start mpv in fullscreen", "fullscreen"),
            _note("Resolution availability ≠ smooth playback. Hardware decoding is only used if mpv "
                  "reports it works; otherwise software decoding takes over, and the player page "
                  "will recommend a lower resolution if frames are dropped. "
                  "Nothing is forced: unsupported options are skipped."),
            rowc, self.hw_text)

    def _set(self, key, value):
        self.s[key] = value
        self._commit()

    def _apply_preset(self):
        self.s.apply_celeron_847_preset()
        self._commit()
        self.win.apply_settings()
        self.q_combo.setCurrentIndex(self.q_combo.findData(self.s["default_quality"]))
        self.hw_combo.setCurrentIndex(self.hw_combo.findData(self.s["hwdec"]))
        self.codec_combo.setCurrentIndex(self.codec_combo.findData(self.s["codec_preference"]))
        self.thr_spin.setValue(self.s["decoder_threads"])
        self.sync_profile_combo()
        self.win.notify("Celeron 847 profile applied: ECO, 360p default, H.264 preferred, hwdec=auto.")

    def _detect(self):
        self.hw_text.setPlainText("Detecting...")
        self.win.runner.submit(hwinfo.detect_system, on_done=self._detected,
                               on_fail=lambda k, m: self.hw_text.setPlainText(m))

    def _detected(self, info):
        text = hwinfo.describe(info)
        mi = self.ctx.mpv_info()
        if mi is not None:
            text += f"\nmpv: {mi.version}\nmpv hwdec options available: " + \
                    (", ".join(sorted(mi.hwdecs)) or "could not be listed")
        else:
            text += "\nmpv: not found"
        if not info.get("machine_64bit", True):
            text += "\n⚠ This is not a 64-bit system: the Qt GUI requires 64-bit Windows."
        self.hw_text.setPlainText(text)

    # -- Ad blocker --------------------------------------------------------
    def _adblock(self):
        self.ab_check = QCheckBox("Enable domain filtering (default: OFF)")
        self.ab_check.setChecked(bool(self.s["adblock"]["enabled"]))
        self.ab_check.toggled.connect(self._ab_toggled)
        self.ab_stats = _note("")
        explain = _note(
            "What it controls: thumbnail downloads made by YouTube Lite, and a host check on stream "
            "addresses before they are handed to mpv or your browser.\n"
            "What it does NOT control: requests made by mpv or by your browser after hand-off, or "
            "ads that are served from the same servers as the video. It does not edit the Windows "
            "hosts file, firewall or browser, and never touches sign-in. YouTube/Google playback "
            "domains are protected and cannot be blocked. Do not expect universal ad removal.")
        self.block_edit = QPlainTextEdit()
        self.allow_edit = QPlainTextEdit()
        self.block_edit.setFixedHeight(100)
        self.allow_edit.setFixedHeight(70)
        b, a = self.ctx.blocker.read_custom()
        self.block_edit.setPlainText(b)
        self.allow_edit.setPlainText(a)
        save = QPushButton("Save custom lists")
        save.clicked.connect(self._ab_save)
        self.url_edit = QLineEdit(self.s["adblock"]["list_url"])
        self.url_edit.editingFinished.connect(self._ab_url)
        self.upd_btn = QPushButton("Update filter list now")
        self.upd_btn.clicked.connect(self._ab_update)
        self.upd_label = _note("")
        return _tab(self.ab_check, self.ab_stats, explain, QLabel("Custom blocklist (one domain per line):"),
                    self.block_edit, QLabel("Allowlist (never blocked):"), self.allow_edit, save,
                    QLabel("Filter list address (https only, updated only when you click):"),
                    self.url_edit, self.upd_btn, self.upd_label)

    def _ab_toggled(self, on):
        self.s["adblock"]["enabled"] = bool(on)
        self.ctx.blocker.enabled = bool(on)
        self._commit()
        self.win.update_indicators()
        self._refresh_adblock()

    def _ab_save(self):
        try:
            self.ctx.blocker.save_custom(self.block_edit.toPlainText(), self.allow_edit.toPlainText())
            self.win.notify("Filter lists saved.")
        except OSError as exc:
            self.win.notify(f"Could not save the lists: {exc}")
        self._refresh_adblock()

    def _ab_url(self):
        self.s["adblock"]["list_url"] = self.url_edit.text().strip()
        self._commit()

    def _ab_update(self):
        url = self.url_edit.text().strip()
        self.s["adblock"]["list_url"] = url
        self.upd_btn.setEnabled(False)
        self.upd_label.setText("Downloading...")
        self.win.runner.submit(lambda: self.ctx.blocker.update_from_url(url),
                               on_done=self._ab_updated, on_fail=self._ab_update_failed)

    def _ab_updated(self, count):
        import datetime
        self.upd_btn.setEnabled(True)
        self.s["adblock"]["last_update"] = datetime.date.today().isoformat()
        self._commit()
        self.upd_label.setText(f"Updated: {count} domains loaded.")
        self._refresh_adblock()

    def _ab_update_failed(self, kind, message):
        self.upd_btn.setEnabled(True)
        self.upd_label.setText("⚠ " + message)

    def _refresh_adblock(self):
        last = self.s["adblock"]["last_update"]
        self.ab_stats.setText(self.ctx.blocker.stats_text() + (f" | list updated {last}" if last else ""))

    # -- Storage -----------------------------------------------------------
    def _storage(self):
        self.st_label = _note("")
        form = QFormLayout()
        self.thumb_spin, self.meta_spin, self.log_spin = QSpinBox(), QSpinBox(), QSpinBox()
        for spin, key, hi in ((self.thumb_spin, "thumb_mb", 500), (self.meta_spin, "meta_mb", 100),
                              (self.log_spin, "log_mb", 20)):
            spin.setRange(1, hi)
            spin.setSuffix(" MB")
            spin.setValue(self.s["cache"][key])
            spin.valueChanged.connect(lambda v, k=key: self._cache_limit(k, v))
        form.addRow("Thumbnail cache limit", self.thumb_spin)
        form.addRow("Metadata cache limit", self.meta_spin)
        form.addRow("Log limit", self.log_spin)
        holder = QWidget()
        holder.setLayout(form)

        def btn(text, fn, danger=False):
            b = QPushButton(text)
            if danger:
                b.setObjectName("Danger")
            b.clicked.connect(fn)
            return b
        row1 = QHBoxLayout()
        for b in (btn("Clear thumbnails", lambda: self._clear("thumbs")),
                  btn("Clear metadata", lambda: self._clear("meta")),
                  btn("Clear all cache", lambda: self._clear("cache"))):
            row1.addWidget(b)
        row1.addStretch(1)
        row2 = QHBoxLayout()
        for b in (btn("Clear search history", lambda: self._clear("searches"), True),
                  btn("Clear recently played", lambda: self._clear("history"), True),
                  btn("Delete ALL local data", lambda: self._clear("all"), True)):
            row2.addWidget(b)
        row2.addStretch(1)
        r1, r2 = QWidget(), QWidget()
        r1.setLayout(row1)
        r2.setLayout(row2)
        open_btn = btn("Open data folder", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.ctx.paths.root))))
        return _tab(self.st_label, holder, r1, r2, open_btn,
                    _note("Videos are never downloaded or stored. Only small thumbnails, search "
                          "results and your lists are kept, inside this folder."))

    def _cache_limit(self, key, value):
        self.s["cache"][key] = value
        self._commit()

    def _clear(self, what: str):
        c = self.ctx
        if what in ("searches", "history", "all"):
            if QMessageBox.question(self, "Confirm", "This cannot be undone. Continue?") \
                    != QMessageBox.StandardButton.Yes:
                return
        if what == "thumbs":
            c.thumb_cache.clear()
            self.win.thumbs.clear_memory()
        elif what == "meta":
            c.meta_cache.clear()
        elif what == "cache":
            c.thumb_cache.clear()
            c.meta_cache.clear()
            self.win.thumbs.clear_memory()
        elif what == "searches":
            c.db(c.storage.clear_searches)
            self.win.refresh_search_completer()
        elif what == "history":
            c.db(c.storage.clear_history)
        elif what == "all":
            c.thumb_cache.clear()
            c.meta_cache.clear()
            self.win.thumbs.clear_memory()
            c.db(c.storage.clear_all)
            self.win.refresh_search_completer()
        self._refresh_storage()
        self.win.notify("Done.")

    def _refresh_storage(self):
        p, c = self.ctx.paths, self.ctx
        log = p.log_file.stat().st_size if p.log_file.exists() else 0
        self.st_label.setText(
            f"Folder: {p.root}\n"
            f"Thumbnails: {_mb(c.thumb_cache.size())} · Metadata: {_mb(c.meta_cache.size())} · "
            f"Logs: {_mb(dir_size(p.logs_dir))} (main log {_mb(log)}) · Database: {_mb(c.storage.file_size())}\n"
            f"Effective limits in {self.s.profile.label} mode: thumbnails "
            f"{_mb(self.s.thumb_limit_bytes())}, metadata {_mb(self.s.meta_limit_bytes())}")

    # -- Appearance --------------------------------------------------------
    def _appearance(self):
        return _tab(
            self._check("Start with the sidebar collapsed", "sidebar_collapsed"),
            self._check("Show duration on thumbnails", "show_duration", self.win.apply_settings),
            self._check("Show view counts", "show_views", self.win.apply_settings),
            _note("The dark theme is fixed. Animations, shadows and blur are intentionally not used."))

    # -- About -------------------------------------------------------------
    def _about(self):
        self.about_text = QLabel("")
        self.about_text.setWordWrap(True)
        self.about_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.mem_label = _note("Memory use of this program has not been measured yet.")
        mem_btn = QPushButton("Measure memory now")
        mem_btn.clicked.connect(self._measure_mem)
        return _tab(self.about_text, mem_btn, self.mem_label,
                    _note("YouTube Lite is an independent project and is not affiliated with or endorsed "
                          "by YouTube or Google. It does not bypass DRM, paid content or sign-in "
                          "requirements. Third-party licenses: see LICENSES.txt."))

    def _refresh_about(self):
        mi = self.ctx.mpv_info()
        self.about_text.setText(
            f"YouTube Lite {__version__}\n"
            f"Python {platform.python_version()} ({'64' if sys.maxsize > 2**32 else '32'}-bit) · "
            f"yt-dlp {ytdlp_version()}\n"
            f"mpv: {mi.version if mi else 'NOT FOUND'}"
            f"{' (bundled)' if self.ctx.paths.mpv_is_bundled() else ''}\n"
            f"mpv location: {self.ctx.mpv_exe() or '-'}\n"
            f"JavaScript runtime (deno, needed for YouTube): {self.ctx.paths.deno_exe() or 'NOT FOUND - videos may not play'}\n"
            f"Uninstall: run Uninstall-YouTube-Lite.bat in this folder, or delete the folder.")

    def _measure_mem(self):
        m = process_memory()
        if not m:
            self.mem_label.setText("Memory could not be read on this system.")
            return
        extra = ""
        if self.win.player.is_running() and self.win.player.proc is not None:
            pm = process_memory(int(self.win.player.proc.processId()))
            if pm:
                extra = f"\nmpv (separate process): working set {pm['working_set_mb']:.0f} MB"
        self.mem_label.setText(
            f"YouTube Lite right now (reported by Windows, measured at this moment): working set "
            f"{m['working_set_mb']:.0f} MB, private {m['private_mb']:.0f} MB, peak working set "
            f"{m['peak_working_set_mb']:.0f} MB.{extra}")
