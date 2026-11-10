"""WIRING SMOKE TEST WITH A FAKE Qt AND A FAKE yt-dlp.

This is NOT a substitute for running the real application. PySide6 may be
unavailable in a CI/sandbox environment; this script executes the GUI modules'
Python code against permissive stand-ins so that typos, wrong attribute names,
bad signatures and broken data flow (search -> grid, extraction -> table ->
mpv command) are caught. It cannot verify real Qt layout, painting, event
behaviour, threading, or mpv.

Run:  python tests/stub_smoke.py
"""
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# ---------------------------------------------------------------- fake Qt ----


class Meta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _make(name)

    def __or__(cls, other):
        return cls


class Dummy(metaclass=Meta):
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        if name.startswith("__") or "_" in name.strip("_"):
            raise AttributeError(name)           # snake_case = one of OUR attributes: don't mask typos
        return Dummy()

    def __call__(self, *a, **k):
        return Dummy()

    def __bool__(self):
        return True

    def __iter__(self):
        return iter(())

    def __or__(self, o):
        return self

    __ror__ = __or__

    def __index__(self):
        return 0

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0


for _op in ("add", "sub", "mul", "floordiv", "truediv"):
    for _pre in ("", "r"):
        setattr(Dummy, f"__{_pre}{_op}__", lambda self, o: 0)
for _op in ("lt", "le", "gt", "ge"):
    setattr(Dummy, f"__{_op}__", lambda self, o: False)

_cache = {}


def _make(name):
    if name not in _cache:
        _cache[name] = Meta(name, (Dummy,), {})
    return _cache[name]


class _Bound:
    def __init__(self):
        self.slots = []

    def connect(self, f, *a, **k):
        self.slots.append(f)

    def disconnect(self, *a):
        self.slots.clear()

    def emit(self, *args):
        for f in list(self.slots):
            f(*args)


class Signal:
    def __init__(self, *types_):
        self.name = None

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        sigs = obj.__dict__.setdefault("_sigs", {})
        return sigs.setdefault(self.name, _Bound())


class QThreadPool(Dummy):
    def start(self, task):
        task.run()                                   # run synchronously for the smoke test

    def clear(self): pass
    def waitForDone(self, *a): return True


class QComboBox(Dummy):
    def __init__(self, *a, **k):
        self.items, self.idx = [], -1

    def addItem(self, text, data=None):
        self.items.append((text, data))
        if self.idx < 0:
            self.idx = 0

    def clear(self): self.items, self.idx = [], -1
    def count(self): return len(self.items)
    def currentData(self): return self.items[self.idx][1] if 0 <= self.idx < len(self.items) else None
    def currentIndex(self): return self.idx
    def setCurrentIndex(self, i): self.idx = i
    def findData(self, d):
        for i, (_t, v) in enumerate(self.items):
            if v == d:
                return i
        return -1


class QLabel(Dummy):
    def __init__(self, text="", *a, **k):
        self._t = text

    def setText(self, t): self._t = t
    def text(self): return self._t
    def clear(self): self._t = ""


class QLineEdit(QLabel):
    pass


class QPlainTextEdit(Dummy):
    def __init__(self, *a, **k): self._t = ""
    def setPlainText(self, t): self._t = t
    def toPlainText(self): return self._t


QTextEdit = QPlainTextEdit


class QSpinBox(Dummy):
    def __init__(self, *a, **k): self._v = 0
    def setValue(self, v): self._v = v
    def value(self): return self._v


class QCheckBox(Dummy):
    def __init__(self, *a, **k): self._c = False
    def setChecked(self, c): self._c = c
    def isChecked(self): return self._c


class QSlider(QSpinBox):
    pass


class _Sel:
    def __init__(self, rows): self.rows = rows
    def selectedRows(self): return [types.SimpleNamespace(row=lambda r=r: r) for r in self.rows]


class QTableWidget(Dummy):
    def __init__(self, *a, **k): self.cells, self.rows_n, self.sel = {}, 0, []
    def setRowCount(self, n): self.rows_n = n
    def rowCount(self): return self.rows_n
    def setItem(self, r, c, it): self.cells[(r, c)] = it
    def selectRow(self, r): self.sel = [r]
    def selectionModel(self): return _Sel(self.sel)


class QTableWidgetItem(Dummy):
    def __init__(self, text="", *a): self._t = text


class QStackedWidget(Dummy):
    def __init__(self, *a, **k): self.w, self.i = [], 0
    def addWidget(self, w): self.w.append(w)
    def setCurrentIndex(self, i): self.i = i
    def currentIndex(self): return self.i
    def currentWidget(self): return self.w[self.i]


class QObject(Dummy):
    pass


class QGridLayout(Dummy):
    def __init__(self, *a, **k): self.n = 0
    def count(self): return self.n
    def takeAt(self, i): self.n = max(0, self.n - 1); return Dummy()
    def addWidget(self, *a): self.n += 1


class _Rect(Dummy):
    def intersects(self, o): return True


def _install():
    for modname in ("PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "PySide6.QtNetwork"):
        mod = types.ModuleType(modname)
        mod.__getattr__ = _make
        sys.modules[modname] = mod
    core = sys.modules["PySide6.QtCore"]
    core.Signal = Signal
    core.QThreadPool = QThreadPool
    core.QObject = QObject
    core.QRect = _Rect
    wid = sys.modules["PySide6.QtWidgets"]
    for cls in (QComboBox, QLabel, QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QCheckBox, QSlider,
                QTableWidget, QTableWidgetItem, QStackedWidget, QGridLayout):
        setattr(wid, cls.__name__, cls)


_install()

# ---------------------------------------------------------------- fake yt-dlp ----


def _entry(i):
    return {"_type": "url", "ie_key": "Youtube", "id": f"vid{i:08d}"[:11], "title": f"Video {i}",
            "url": f"https://www.youtube.com/watch?v=vid{i:08d}"[:43], "duration": 60 + i,
            "view_count": 1000 * i, "channel": "Chan", "channel_id": "UC123",
            "channel_url": "https://www.youtube.com/channel/UC123",
            "thumbnails": [{"url": f"https://i.ytimg.com/vi/{i}/hq.jpg", "width": 336}]}


def _fmt(fid, h, vcodec="avc1.4d401f", acodec="none", tbr=500):
    return {"format_id": fid, "url": f"https://rr1.googlevideo.com/{fid}", "height": h, "width": h * 16 // 9,
            "vcodec": vcodec, "acodec": acodec, "fps": 30, "tbr": tbr, "protocol": "https", "ext": "mp4"}


class FakeYDL:
    calls = []

    def __init__(self, opts): self.opts = opts
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def extract_info(self, target, download=False):
        FakeYDL.calls.append((target, dict(self.opts)))
        if "watch?v=" in target:
            return {"title": "Real Title", "channel": "Chan", "duration": 300, "view_count": 5,
                    "upload_date": "20240131", "description": "desc",
                    "formats": [_fmt("134", 360), _fmt("135", 480), _fmt("136", 720), _fmt("137", 1080),
                                {"format_id": "140", "url": "https://rr1.googlevideo.com/140",
                                 "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "protocol": "https"}]}
        n = int(self.opts["playlist_items"].split("-")[1]) - int(self.opts["playlist_items"].split("-")[0]) + 1
        return {"entries": [_entry(i) for i in range(n)], "channel": "Chan"}


yt = types.ModuleType("yt_dlp")
yt.YoutubeDL = FakeYDL
yt.version = types.SimpleNamespace(__version__="0.0-fake")
sys.modules["yt_dlp"] = yt

# ---------------------------------------------------------------- the test ----

from ytlite.app import AppContext                      # noqa: E402
from ytlite.gui.mainwindow import MainWindow           # noqa: E402


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        check.failed += 1


check.failed = 0


def main():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = AppContext(tmp)
        win = MainWindow(ctx)
        check(len(win.pages) == 9, "MainWindow builds all 9 pages")
        for i in range(9):
            win.go(i)
        win.go(0)
        check(True, "every page can be shown / refreshed")

        # --- search flow: header -> ResultsView -> yt-dlp(fake) -> grid cards
        win.search_box.text = lambda: "cats"
        win.do_search()
        grid = win.search_page.grid
        check(len(grid.items) == ctx.settings.profile.results == 10, "ECO search returns 10 items into the grid")
        check(ctx.storage.recent_searches() == ["cats"], "search saved to history")
        target, opts = FakeYDL.calls[-1]
        check(target == "ytsearch10:cats" and opts["playlist_items"] == "1-10", "yt-dlp asked for ytsearch10, items 1-10")
        check(opts["extract_flat"] == "in_playlist" and opts["skip_download"], "flat extraction, no download")
        check(grid.cards[0].item.title == "Video 0" and len(grid.cards) == 10, "10 reusable card widgets created")

        # --- pagination reuses the same card widgets
        before = list(grid.cards)
        win.search_page.results._goto(2)
        check(FakeYDL.calls[-1][1]["playlist_items"] == "11-20", "page 2 requests items 11-20")
        check(grid.cards == before, "cards are reused across pages")

        # --- cache hit avoids a second request
        n = len(FakeYDL.calls)
        win.search_page.results._goto(2)
        check(len(FakeYDL.calls) == n, "repeat of the same page is served from the metadata cache")

        # --- live profile switch (no restart)
        ctx.settings["profile"] = "quality"
        win.apply_settings()
        win.search_page.results.load({"t": "video", "q": "dogs"}, 1)
        check(len(grid.items) == 20, "QUALITY mode switches to 20 results without restart")
        ctx.settings["profile"] = "eco"
        win.apply_settings()

        # --- play: extraction -> quality table -> mpv command
        item = grid.items[0]
        launched = {}
        win.player.launch = lambda vid, opt, title, start=0.0: launched.update(vid=vid, opt=opt, title=title, start=start) or True
        win.play(item)
        pp = win.player_page
        check(pp.table.rowCount() == 4, "quality table lists 360/480/720/1080")
        check(launched.get("opt") is not None and launched["opt"].height == 360, "ECO auto-play picks 360p by default")
        check(launched["opt"].audio_url.endswith("/140"), "DASH audio passed separately")
        check(ctx.storage.history_count() == 1, "play recorded in Recently played")
        pp.table.selectRow(2)
        pp.open_selected()
        check(launched["opt"].height == 720 and launched["opt"].codec == "h264", "manual 720p H.264 selection works")
        pp.table.selectRow(3)
        pp.open_selected()
        check(launched["opt"].height == 1080, "manual 1080p selection is allowed")

        # --- blocker never blocks playback hosts, and obeys the toggle
        ctx.blocker.enabled = True
        ctx.blocker.save_custom("googlevideo.com\nads.test\n", "")
        launched.clear()
        pp.open_selected()
        check(bool(launched), "googlevideo.com is protected: playback not blocked")
        check(ctx.blocker.check_url("https://x.ads.test/a"), "custom blocklist entry blocks when ON")
        ctx.blocker.enabled = False
        check(not ctx.blocker.check_url("https://x.ads.test/a"), "nothing blocked when OFF")

        # --- menu actions & DB pages
        win._wl_add(item)
        win.go(5)
        check(win.watch_later.grid.items and win.watch_later.grid.items[0].id == item.id, "Watch Later shows the saved video")
        pid = ctx.storage.create_playlist("Mix")
        win._pl_add(pid, item)
        win.go(6)
        check(len(win.playlists.grid.items) == 1, "Playlists page lists playlist items")
        win.go(4)
        check(len(win.history.grid.items) == 1, "History page lists the played video")
        win._remove_from_context(item, "history")
        check(ctx.storage.history_count() == 0, "history entry removed individually")

        # --- storage page / cache cleanup
        ctx.thumb_cache.write("https://i.ytimg.com/x", b"abc")
        win.settings_page._clear("thumbs")
        check(ctx.thumb_cache.size() == 0, "Clear thumbnails empties the thumbnail cache")
        win.settings_page._clear("cache")
        check(ctx.meta_cache.size() == 0, "Clear all cache empties metadata cache")

        # --- settings persisted into the portable folder
        check(ctx.save_settings() and (Path(tmp) / "config" / "settings.json").exists(), "settings.json written in portable folder")
        saved = json.loads((Path(tmp) / "config" / "settings.json").read_text())
        check(saved["adblock"]["enabled"] is False, "ad blocker default/off persisted")
        check((Path(tmp) / "data" / "history.db").exists(), "history.db in portable folder")
        check((Path(tmp) / "mpv" / "mpv.conf").exists(), "default mpv.conf created")

        win.close()
    print(f"\n{'ALL PASSED' if not check.failed else str(check.failed) + ' FAILED'}")
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
