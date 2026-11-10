"""Main window: header, collapsible sidebar and the page stack."""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import QPoint, QStringListModel, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QFrame, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from .. import APP_NAME
from ..config import PROFILES
from ..search import VideoItem
from .pages import (HomePage, LibraryPage, PlayerPage, PlaylistsPage, SearchPage,
                    SubscriptionsPage, TrendingPage)
from .playback import PlayerController
from .settings_page import SettingsPage
from .thumbs import ThumbLoader
from .workers import TaskRunner

NAV = (("Home", "⌂"), ("Search", "⌕"), ("Trending", "↗"), ("Subscriptions", "☆"),
       ("History", "↺"), ("Watch Later", "◷"), ("Playlists", "☰"), ("Settings", "⚙"))
PAGE_PLAYER = 8


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        ctx.notify = self.notify
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 680)
        self.setMinimumSize(900, 520)           # comfortable at 1024x600

        self.runner = TaskRunner(self)
        self.thumbs = ThumbLoader(ctx, self)
        self.player = PlayerController(ctx, self)
        self._prev_index = 0

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)

        self.home = HomePage(self)
        self.search_page = SearchPage(self)
        self.trending = TrendingPage(self)
        self.subs = SubscriptionsPage(self)
        self.history = LibraryPage(self, "history", "History")
        self.watch_later = LibraryPage(self, "watch_later", "Watch Later")
        self.playlists = PlaylistsPage(self)
        self.settings_page = SettingsPage(self)
        self.player_page = PlayerPage(self)
        self.pages = [self.home, self.search_page, self.trending, self.subs, self.history,
                      self.watch_later, self.playlists, self.settings_page, self.player_page]
        for p in self.pages:
            self.stack.addWidget(p)

        # (page grid, context name) -> activation + context menu wiring
        grids = {self.home: ("home", self.home.grid), self.search_page: ("search", self.search_page.grid),
                 self.trending: ("search", self.trending.grid), self.subs: ("subs", self.subs.grid),
                 self.history: ("history", self.history.grid),
                 self.watch_later: ("watch_later", self.watch_later.grid),
                 self.playlists: ("playlist", self.playlists.grid)}
        for page, (context, grid) in grids.items():
            grid.activated.connect(self._on_card)
            grid.menuRequested.connect(lambda item, pos, c=context: self.show_item_menu(item, pos, c))

        self.statusBar().setSizeGripEnabled(False)
        self.apply_settings()
        self.go(0)
        self.refresh_search_completer()
        self._startup_notices()

    # -- construction ------------------------------------------------------
    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Header")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 6, 10, 6)
        lay.setSpacing(8)
        logo = QLabel('<span style="color:#2878E5;">▶</span> YouTube Lite')
        logo.setObjectName("Logo")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search YouTube (nothing loads until you search)")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.returnPressed.connect(self.do_search)
        self.completer = QCompleter(QStringListModel(self), self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search_box.setCompleter(self.completer)
        go = QPushButton("Search")
        go.setObjectName("Primary")
        go.clicked.connect(self.do_search)
        self.mode_combo = QComboBox()
        for key, p in PROFILES.items():
            self.mode_combo.addItem(p.label, key)
        self.mode_combo.setToolTip("Performance mode (applies immediately)")
        self.mode_combo.currentIndexChanged.connect(self._mode_combo_changed)
        self.adblock_label = QLabel("")
        self.adblock_label.setObjectName("Pill")
        self.adblock_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.adblock_label.mousePressEvent = lambda _e: self.open_settings("Ad blocker")
        gear = QToolButton()
        gear.setText("⚙")
        gear.setToolTip("Settings")
        gear.clicked.connect(lambda: self.open_settings("General"))
        lay.addWidget(logo)
        lay.addWidget(self.search_box, 1)
        lay.addWidget(go)
        lay.addWidget(self.mode_combo)
        lay.addWidget(self.adblock_label)
        lay.addWidget(gear)
        return bar

    def _build_sidebar(self) -> QWidget:
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        lay = QVBoxLayout(self.sidebar)
        lay.setContentsMargins(6, 8, 6, 8)
        lay.setSpacing(2)
        self.collapse_btn = QToolButton()
        self.collapse_btn.setObjectName("Nav")
        self.collapse_btn.setText("☰")
        self.collapse_btn.setToolTip("Collapse / expand sidebar")
        self.collapse_btn.clicked.connect(lambda: self.set_sidebar_collapsed(not self._collapsed))
        lay.addWidget(self.collapse_btn)
        self.nav_buttons: list[QToolButton] = []
        for i, (name, glyph) in enumerate(NAV):
            b = QToolButton()
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setText(f"{glyph}  {name}")
            b.setToolTip(name)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            b.setSizePolicy(b.sizePolicy().horizontalPolicy(), b.sizePolicy().verticalPolicy())
            b.clicked.connect(lambda _c=False, idx=i: self.go(idx))
            lay.addWidget(b)
            self.nav_buttons.append(b)
        lay.addStretch(1)
        self._collapsed = False
        return self.sidebar

    def set_sidebar_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.sidebar.setFixedWidth(52 if collapsed else 172)
        for b, (name, glyph) in zip(self.nav_buttons, NAV):
            b.setText(glyph if collapsed else f"{glyph}  {name}")
            b.setMinimumWidth(0 if collapsed else 150)
        self.collapse_btn.setMinimumWidth(0 if collapsed else 150)
        self.ctx.settings["sidebar_collapsed"] = collapsed
        self.ctx.save_settings()

    def _startup_notices(self):
        if self.ctx.problems:
            self.notify("Some folders could not be created: " + "; ".join(self.ctx.problems[:2]))
        elif not self.ctx.writable:
            self.notify("This folder is read-only: settings and history cannot be saved.")
        elif self.ctx.settings.last_error:
            self.notify(self.ctx.settings.last_error)
        elif not self.ctx.storage.available:
            self.notify(self.ctx.storage.error)

    # -- navigation --------------------------------------------------------
    def go(self, index: int) -> None:
        if index != PAGE_PLAYER:
            self._prev_index = index
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self.nav_buttons):
            b.setChecked(i == index)
        page = self.pages[index]
        if hasattr(page, "refresh"):
            page.refresh()

    def open_settings(self, tab: str) -> None:
        self.go(7)
        self.settings_page.show_tab(tab)

    def return_to_app(self) -> None:
        self.go(self._prev_index if self._prev_index != PAGE_PLAYER else 0)
        self.showNormal() if self.isMinimized() else None
        self.raise_()
        self.activateWindow()

    # -- search ------------------------------------------------------------
    def do_search(self) -> None:
        q = self.search_box.text().strip()
        if not q:
            self.notify("Type something to search for.")
            return
        if self.ctx.settings["save_search_history"] and self.ctx.storage.available:
            self.ctx.db(self.ctx.storage.add_search, q)
            self.refresh_search_completer()
        self.go(1)
        self.search_page.search(q)

    def refresh_search_completer(self) -> None:
        items = self.ctx.db(self.ctx.storage.recent_searches, 20, default=[]) if self.ctx.storage.available else []
        self.completer.model().setStringList(items or [])

    # -- actions -----------------------------------------------------------
    def _on_card(self, item: VideoItem) -> None:
        if item.kind == "channel":
            self.open_channel(item)
        else:
            self.play(item)

    def play(self, item: VideoItem) -> None:
        self.go(PAGE_PLAYER)
        self.player_page.start(item)

    def open_channel(self, item: VideoItem) -> None:
        self.go(1)
        self.search_page.open_channel(item)

    def open_web(self, item: VideoItem) -> None:
        url = f"https://www.youtube.com/watch?v={item.id}" if item.kind == "video" else item.url
        if self.ctx.settings["confirm_web_mode"]:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Web Mode")
            box.setText("Open this video in your web browser?")
            box.setInformativeText("Browsers can use several hundred MB of memory and may slow down "
                                   "this laptop. The native player is much lighter.")
            check = QCheckBox("Don't ask again")
            box.setCheckBox(check)
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.No)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
            if check.isChecked():
                self.ctx.settings["confirm_web_mode"] = False
                self.ctx.save_settings()
        if self.ctx.blocker.check_url(url):
            self.notify("The ad blocker refused this address.")
            return
        if not webbrowser.open(url):
            self.notify("No web browser could be opened.")

    def show_item_menu(self, item: VideoItem, pos: QPoint, context: str) -> None:
        st = self.ctx.storage
        menu = QMenu(self)
        if item.kind == "channel":
            menu.addAction("Open channel videos", lambda: self.open_channel(item))
            if context == "subs":
                menu.addAction("Remove channel", lambda: self._remove_channel(item))
            else:
                menu.addAction("Save channel locally", lambda: self._save_channel(item))
            menu.exec(pos)
            return
        menu.addAction("▶  Play", lambda: self.play(item))
        later = self.ctx.db(st.in_watch_later, item.id, default=False)
        if later:
            menu.addAction("Remove from Watch Later", lambda: self._wl_remove(item))
        else:
            menu.addAction("Add to Watch Later", lambda: self._wl_add(item))
        sub = menu.addMenu("Add to playlist")
        for p in self.ctx.db(st.playlists, default=[]) or []:
            sub.addAction(f"{p['name']} ({p['count']})", lambda pid=p["id"]: self._pl_add(pid, item))
        sub.addSeparator()
        sub.addAction("New playlist…", lambda: self._pl_new_and_add(item))
        menu.addSeparator()
        if item.channel_url:
            menu.addAction("Open channel videos", lambda: self.open_channel(
                VideoItem("channel", item.channel_id, item.channel, item.channel, item.channel_id,
                          item.channel_url, None, None, "", item.channel_url)))
            menu.addAction("Save channel locally", lambda: self._save_channel(VideoItem(
                "channel", item.channel_id or item.channel, item.channel, item.channel,
                item.channel_id, item.channel_url, None, None, "", item.channel_url)))
        menu.addAction("Open in browser (Web Mode)", lambda: self.open_web(item))
        menu.addAction("Copy link", lambda: QGuiApplication.clipboard().setText(
            f"https://www.youtube.com/watch?v={item.id}"))
        if context in ("history", "watch_later", "playlist"):
            menu.addSeparator()
            menu.addAction("Remove from this list", lambda: self._remove_from_context(item, context))
        menu.exec(pos)

    def _wl_add(self, item):
        added = self.ctx.db(self.ctx.storage.add_watch_later, item.to_dict(), default=None)
        if added is not None:
            self.notify("Added to Watch Later." if added else "Already in Watch Later.")

    def _wl_remove(self, item):
        self.ctx.db(self.ctx.storage.remove_watch_later, item.id)
        self.notify("Removed from Watch Later.")
        self._refresh_current()

    def _pl_add(self, pid, item):
        added = self.ctx.db(self.ctx.storage.add_to_playlist, pid, item.to_dict(), default=None)
        if added is not None:
            self.notify("Added to playlist." if added else "Already in that playlist.")

    def _pl_new_and_add(self, item):
        name, ok = QInputDialog.getText(self, "New playlist", "Name:")
        if ok and name.strip():
            pid = self.ctx.db(self.ctx.storage.create_playlist, name)
            if pid is not None:
                self._pl_add(pid, item)

    def _save_channel(self, item):
        saved = self.ctx.db(self.ctx.storage.save_channel, item.to_dict(), default=None)
        if saved is not None:
            self.notify("Channel saved under Subscriptions." if saved else "Channel already saved.")

    def _remove_channel(self, item):
        self.ctx.db(self.ctx.storage.remove_channel, item.channel_id or item.id)
        self.subs.refresh()

    def _remove_from_context(self, item, context):
        st = self.ctx.storage
        if context == "history":
            self.ctx.db(st.remove_history, item.id)
        elif context == "watch_later":
            self.ctx.db(st.remove_watch_later, item.id)
        elif context == "playlist" and self.playlists.current_id is not None:
            self.ctx.db(st.remove_from_playlist, self.playlists.current_id, item.id)
        self._refresh_current()

    def _refresh_current(self):
        page = self.stack.currentWidget()
        if hasattr(page, "refresh"):
            page.refresh()

    # -- settings / indicators --------------------------------------------
    def _mode_combo_changed(self) -> None:
        key = self.mode_combo.currentData()
        if key and key != self.ctx.settings["profile"]:
            self.ctx.settings["profile"] = key
            self.ctx.save_settings()
            self.apply_settings()

    def apply_settings(self) -> None:
        """Re-apply everything that depends on settings (no restart needed)."""
        s = self.ctx.settings
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(s["profile"]))
        self.mode_combo.blockSignals(False)
        self.settings_page.sync_profile_combo()
        self.set_sidebar_collapsed(bool(s["sidebar_collapsed"])) if self._collapsed != s["sidebar_collapsed"] \
            else self.set_sidebar_collapsed(self._collapsed)
        self.update_indicators()
        for page in self.pages:
            grid = getattr(page, "grid", None)
            if grid is not None and hasattr(grid, "refresh_profile"):
                grid.refresh_profile()
        self.thumbs.clear_memory()

    def update_indicators(self) -> None:
        on = self.ctx.blocker.enabled
        self.adblock_label.setText("Ad block: ON" if on else "Ad block: OFF")
        self.adblock_label.setStyleSheet("color:#4FBF7F;" if on else "")

    def notify(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)

    # -- shutdown ----------------------------------------------------------
    def closeEvent(self, ev):
        try:
            self.player.stop()                 # never leave mpv behind
            self.thumbs.cancel_pending()
            self.runner.shutdown()
            self.ctx.save_settings()
        finally:
            self.ctx.shutdown()
        ev.accept()
