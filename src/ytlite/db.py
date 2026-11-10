"""Local SQLite storage: search history, recently played, watch later,
playlists and locally saved channels. No account, no cloud, no personal data.

All access happens on the GUI thread (single connection).
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

MAX_HISTORY = 500
MAX_SEARCHES = 50

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches(
    q TEXT PRIMARY KEY, ts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS history(
    vid TEXT PRIMARY KEY, title TEXT, channel TEXT, channel_id TEXT,
    duration INTEGER, thumb TEXT, ts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS watch_later(
    vid TEXT PRIMARY KEY, title TEXT, channel TEXT, channel_id TEXT,
    duration INTEGER, thumb TEXT, ts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS playlists(
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, ts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS playlist_items(
    pid INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    vid TEXT NOT NULL, title TEXT, channel TEXT, channel_id TEXT,
    duration INTEGER, thumb TEXT, ts INTEGER NOT NULL,
    PRIMARY KEY(pid, vid));
CREATE TABLE IF NOT EXISTS channels(
    cid TEXT PRIMARY KEY, name TEXT, url TEXT, thumb TEXT, ts INTEGER NOT NULL);
"""

_VIDEO_COLS = ("vid", "title", "channel", "channel_id", "duration", "thumb")


class StorageError(Exception):
    pass


def _video_row(v: dict) -> tuple:
    return (str(v.get("id", ""))[:32], str(v.get("title", ""))[:300],
            str(v.get("channel", ""))[:200], str(v.get("channel_id", ""))[:64],
            v.get("duration") if isinstance(v.get("duration"), int) else None,
            str(v.get("thumb_url", ""))[:500])


def _to_video(row: sqlite3.Row) -> dict:
    return {"kind": "video", "id": row["vid"], "title": row["title"] or "",
            "channel": row["channel"] or "", "channel_id": row["channel_id"] or "",
            "channel_url": "", "duration": row["duration"], "views": None,
            "thumb_url": row["thumb"] or "",
            "url": f"https://www.youtube.com/watch?v={row['vid']}"}


class Storage:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.conn: sqlite3.Connection | None = None
        self.error: str = ""

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(self.path), timeout=5)
            self.conn.row_factory = sqlite3.Row
            # Rollback journal + FULL sync: safest for removable drives (no -wal files).
            self.conn.execute("PRAGMA journal_mode=DELETE")
            self.conn.execute("PRAGMA synchronous=FULL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.executescript(SCHEMA)
            self.conn.commit()
            self.error = ""
            return True
        except (sqlite3.Error, OSError) as exc:
            self.conn = None
            self.error = f"Database unavailable: {exc}"
            return False

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
            self.conn = None

    @property
    def available(self) -> bool:
        return self.conn is not None

    def _run(self, sql: str, args: tuple = (), *, write: bool = False):
        if self.conn is None:
            raise StorageError(self.error or "Database is not open.")
        try:
            cur = self.conn.execute(sql, args)
            if write:
                self.conn.commit()
            return cur
        except sqlite3.Error as exc:
            self.error = f"Database error: {exc}"
            raise StorageError(self.error) from exc

    # -- search history ----------------------------------------------------
    def add_search(self, q: str) -> None:
        q = q.strip()[:200]
        if not q:
            return
        self._run("INSERT INTO searches(q, ts) VALUES(?,?) "
                  "ON CONFLICT(q) DO UPDATE SET ts=excluded.ts", (q, int(time.time())), write=True)
        self._run("DELETE FROM searches WHERE q NOT IN "
                  "(SELECT q FROM searches ORDER BY ts DESC LIMIT ?)", (MAX_SEARCHES,), write=True)

    def recent_searches(self, limit: int = 20) -> list[str]:
        return [r["q"] for r in self._run(
            "SELECT q FROM searches ORDER BY ts DESC LIMIT ?", (limit,))]

    def delete_search(self, q: str) -> None:
        self._run("DELETE FROM searches WHERE q=?", (q,), write=True)

    def clear_searches(self) -> None:
        self._run("DELETE FROM searches", write=True)

    # -- recently played ---------------------------------------------------
    def add_history(self, v: dict) -> None:
        row = _video_row(v)
        if not row[0]:
            return
        self._run("INSERT INTO history(vid,title,channel,channel_id,duration,thumb,ts) "
                  "VALUES(?,?,?,?,?,?,?) ON CONFLICT(vid) DO UPDATE SET "
                  "title=excluded.title, channel=excluded.channel, thumb=excluded.thumb, "
                  "ts=excluded.ts", (*row, int(time.time())), write=True)
        self._run("DELETE FROM history WHERE vid NOT IN "
                  "(SELECT vid FROM history ORDER BY ts DESC LIMIT ?)", (MAX_HISTORY,), write=True)

    def history(self, limit: int = 20, offset: int = 0) -> list[dict]:
        return [_to_video(r) for r in self._run(
            "SELECT * FROM history ORDER BY ts DESC LIMIT ? OFFSET ?", (limit, offset))]

    def history_count(self) -> int:
        return self._run("SELECT COUNT(*) c FROM history").fetchone()["c"]

    def remove_history(self, vid: str) -> None:
        self._run("DELETE FROM history WHERE vid=?", (vid,), write=True)

    def clear_history(self) -> None:
        self._run("DELETE FROM history", write=True)

    # -- watch later -------------------------------------------------------
    def add_watch_later(self, v: dict) -> bool:
        """Returns False if it was already saved."""
        row = _video_row(v)
        if not row[0]:
            return False
        if self.in_watch_later(row[0]):
            return False
        self._run("INSERT INTO watch_later(vid,title,channel,channel_id,duration,thumb,ts) "
                  "VALUES(?,?,?,?,?,?,?)", (*row, int(time.time())), write=True)
        return True

    def in_watch_later(self, vid: str) -> bool:
        return self._run("SELECT 1 FROM watch_later WHERE vid=?", (vid,)).fetchone() is not None

    def watch_later(self, limit: int = 20, offset: int = 0) -> list[dict]:
        return [_to_video(r) for r in self._run(
            "SELECT * FROM watch_later ORDER BY ts DESC LIMIT ? OFFSET ?", (limit, offset))]

    def watch_later_count(self) -> int:
        return self._run("SELECT COUNT(*) c FROM watch_later").fetchone()["c"]

    def remove_watch_later(self, vid: str) -> None:
        self._run("DELETE FROM watch_later WHERE vid=?", (vid,), write=True)

    def clear_watch_later(self) -> None:
        self._run("DELETE FROM watch_later", write=True)

    # -- playlists ---------------------------------------------------------
    def create_playlist(self, name: str) -> int:
        name = name.strip()[:80]
        if not name:
            raise StorageError("Playlist name cannot be empty.")
        try:
            cur = self._run("INSERT INTO playlists(name, ts) VALUES(?,?)",
                            (name, int(time.time())), write=True)
        except StorageError as exc:
            raise StorageError(f"A playlist named '{name}' already exists.") from exc
        return int(cur.lastrowid)

    def rename_playlist(self, pid: int, name: str) -> None:
        name = name.strip()[:80]
        if not name:
            raise StorageError("Playlist name cannot be empty.")
        self._run("UPDATE playlists SET name=? WHERE id=?", (name, pid), write=True)

    def delete_playlist(self, pid: int) -> None:
        self._run("DELETE FROM playlist_items WHERE pid=?", (pid,), write=True)
        self._run("DELETE FROM playlists WHERE id=?", (pid,), write=True)

    def playlists(self) -> list[dict]:
        return [{"id": r["id"], "name": r["name"], "count": r["n"]} for r in self._run(
            "SELECT p.id, p.name, COUNT(i.vid) n FROM playlists p "
            "LEFT JOIN playlist_items i ON i.pid=p.id GROUP BY p.id ORDER BY p.name COLLATE NOCASE")]

    def add_to_playlist(self, pid: int, v: dict) -> bool:
        row = _video_row(v)
        if not row[0]:
            return False
        exists = self._run("SELECT 1 FROM playlist_items WHERE pid=? AND vid=?",
                           (pid, row[0])).fetchone()
        if exists:
            return False
        self._run("INSERT INTO playlist_items(pid,vid,title,channel,channel_id,duration,thumb,ts) "
                  "VALUES(?,?,?,?,?,?,?,?)", (pid, *row, int(time.time())), write=True)
        return True

    def playlist_items(self, pid: int, limit: int = 20, offset: int = 0) -> list[dict]:
        return [_to_video(r) for r in self._run(
            "SELECT * FROM playlist_items WHERE pid=? ORDER BY ts ASC LIMIT ? OFFSET ?",
            (pid, limit, offset))]

    def playlist_count(self, pid: int) -> int:
        return self._run("SELECT COUNT(*) c FROM playlist_items WHERE pid=?",
                         (pid,)).fetchone()["c"]

    def remove_from_playlist(self, pid: int, vid: str) -> None:
        self._run("DELETE FROM playlist_items WHERE pid=? AND vid=?", (pid, vid), write=True)

    # -- locally saved channels ("Subscriptions") ---------------------------
    def save_channel(self, c: dict) -> bool:
        cid = str(c.get("channel_id") or c.get("id") or "")[:64]
        url = str(c.get("url") or c.get("channel_url") or "")[:300]
        if not cid or not url:
            return False
        cur = self._run("INSERT OR IGNORE INTO channels(cid,name,url,thumb,ts) VALUES(?,?,?,?,?)",
                        (cid, str(c.get("title") or c.get("channel") or "")[:200], url,
                         str(c.get("thumb_url", ""))[:500], int(time.time())), write=True)
        return cur.rowcount > 0

    def channels(self) -> list[dict]:
        return [{"kind": "channel", "id": r["cid"], "title": r["name"] or "",
                 "channel": r["name"] or "", "channel_id": r["cid"], "channel_url": r["url"],
                 "url": r["url"], "thumb_url": r["thumb"] or "", "duration": None, "views": None}
                for r in self._run("SELECT * FROM channels ORDER BY name COLLATE NOCASE")]

    def remove_channel(self, cid: str) -> None:
        self._run("DELETE FROM channels WHERE cid=?", (cid,), write=True)

    # -- maintenance -------------------------------------------------------
    def clear_all(self) -> None:
        for table in ("searches", "history", "watch_later", "playlist_items",
                      "playlists", "channels"):
            self._run(f"DELETE FROM {table}", write=True)
        try:
            self._run("VACUUM")
        except StorageError:
            pass

    def file_size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0
