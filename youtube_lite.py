# YouTube Lite — ASUS Edition
# Windows 10 64-bit | Tkinter + libmpv + yt-dlp + YouTube Data API v3
#
# This application searches public YouTube metadata through the official API.
# Playback is delegated to MPV's ytdl_hook, which uses yt-dlp.
# It does not download or save video files.

import json
import os
import shutil
import sys
import sysconfig
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

APP_NAME = "YouTube Lite"
_DLL_DIRECTORY_HANDLES = []
APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "YouTubeLite"
CONFIG_FILE = APP_DIR / "settings.json"

DEFAULTS = {
    "api_key": "",
    "quality": "360",
    "fps": "30",
    "hwdec": "auto-safe",
    "volume": 70,
}

def load_settings():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return {**DEFAULTS, **data}
    except Exception:
        return DEFAULTS.copy()

def save_settings(settings):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(settings, indent=2), encoding="utf-8"
    )

def api_search(api_key, query, kind="video"):
    if not api_key.strip():
        raise RuntimeError("Add your YouTube Data API key in Settings first.")

    params = {
        "part": "snippet",
        "q": query,
        "type": kind,
        "maxResults": 15,
        "key": api_key.strip(),
    }
    url = "https://www.googleapis.com/youtube/v3/search?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "YouTubeLite-ASUS/1.0"})
    with urlopen(req, timeout=18) as response:
        payload = json.loads(response.read().decode("utf-8"))

    results = []
    for item in payload.get("items", []):
        snippet = item.get("snippet", {})
        ident = item.get("id", {})
        if kind == "playlist":
            item_id = ident.get("playlistId")
        else:
            item_id = ident.get("videoId")
        if not item_id:
            continue
        results.append({
            "id": item_id,
            "kind": kind,
            "title": snippet.get("title", "(untitled)"),
            "channel": snippet.get("channelTitle", ""),
            "date": snippet.get("publishedAt", "")[:10],
        })
    return results

def find_mpv_directory():
    candidates = []
    env_dir = os.environ.get("MPV_HOME")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates += [
        Path(__file__).resolve().parent / "mpv",
        Path(__file__).resolve().parent,
        Path(r"C:\mpv"),
        Path(r"C:\Program Files\mpv"),
    ]
    for folder in candidates:
        if (folder / "mpv-2.dll").exists() or (folder / "libmpv-2.dll").exists():
            return folder
    return None

def prepare_mpv_import():
    folder = find_mpv_directory()
    if not folder:
        raise RuntimeError(
            "MPV DLL not found.\n\n"
            "Download a 64-bit MPV Windows build, extract it, and place "
            "mpv-2.dll (or libmpv-2.dll) in a folder named 'mpv' beside "
            "youtube_lite.py. See README.txt."
        )
    os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(folder)))
    # MPV's ytdl_hook searches PATH for yt-dlp. Add Python's Scripts folder
    # even when the installer did not add it to the user's PATH.
    scripts = sysconfig.get_path("scripts")
    if scripts and Path(scripts).exists():
        os.environ["PATH"] = scripts + os.pathsep + os.environ["PATH"]
    ytdlp = shutil.which("yt-dlp.exe") or shutil.which("yt-dlp")
    if ytdlp:
        scripts_dir = str(Path(ytdlp).resolve().parent)
        os.environ["PATH"] = scripts_dir + os.pathsep + os.environ["PATH"]
    return folder

class YouTubeLite:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.results = []
        self.player = None
        self.player_ready = False
        self.search_busy = False
        self.closing = False

        root.title("YouTube Lite — ASUS Edition")
        root.geometry("1000x680")
        root.minsize(720, 500)
        root.configure(bg="#080808")
        root.protocol("WM_DELETE_WINDOW", self.close)

        self._build_ui()
        self._init_player()

    def _build_ui(self):
        top = tk.Frame(self.root, bg="#111111", height=58)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(
            top, text="▶  YouTube Lite", bg="#111111", fg="white",
            font=("Segoe UI", 17, "bold")
        ).pack(side="left", padx=16)

        tk.Button(
            top, text="⚙ Settings", command=self.open_settings,
            bg="#252525", fg="white", activebackground="#333333",
            activeforeground="white", relief="flat", padx=12
        ).pack(side="right", padx=12, pady=12)

        searchbar = tk.Frame(self.root, bg="#080808")
        searchbar.pack(fill="x", padx=14, pady=(12, 8))

        self.query = tk.Entry(
            searchbar, bg="#1b1b1b", fg="white",
            insertbackground="white", relief="flat",
            font=("Segoe UI", 11)
        )
        self.query.pack(side="left", fill="x", expand=True, ipady=9)
        self.query.bind("<Return>", lambda _e: self.search())

        self.kind = tk.StringVar(value="video")
        ttk.Style().configure("Lite.TCombobox", padding=5)
        self.kind_box = ttk.Combobox(
            searchbar, textvariable=self.kind,
            values=("video", "playlist"), state="readonly",
            width=10
        )
        self.kind_box.pack(side="left", padx=7)

        self.search_button = tk.Button(
            searchbar, text="Search", command=self.search,
            bg="#e6002e", fg="white", activebackground="#c90028",
            activeforeground="white", relief="flat", padx=16
        )
        self.search_button.pack(side="left")

        self.status = tk.StringVar(value="Ready — search videos or playlists.")
        tk.Label(
            self.root, textvariable=self.status,
            bg="#080808", fg="#999999", anchor="w",
            font=("Segoe UI", 9)
        ).pack(fill="x", padx=15, pady=(0, 7))

        content = tk.PanedWindow(
            self.root, orient="horizontal", bg="#080808",
            sashwidth=5, bd=0, relief="flat"
        )
        content.pack(fill="both", expand=True, padx=12, pady=4)

        left = tk.Frame(content, bg="#101010")
        right = tk.Frame(content, bg="#101010")
        content.add(left, minsize=260, width=340)
        content.add(right, minsize=360)

        tk.Label(
            left, text="SEARCH RESULTS", bg="#101010", fg="#bbbbbb",
            font=("Segoe UI", 9, "bold"), anchor="w"
        ).pack(fill="x", padx=10, pady=9)

        self.listbox = tk.Listbox(
            left, bg="#151515", fg="#eeeeee",
            selectbackground="#a90024", selectforeground="white",
            activestyle="none", relief="flat", borderwidth=0,
            font=("Segoe UI", 9), highlightthickness=0
        )
        self.listbox.pack(fill="both", expand=True, padx=7, pady=(0, 7))
        self.listbox.bind("<Double-Button-1>", lambda _e: self.play_selected())

        tk.Button(
            left, text="▶  Play selected", command=self.play_selected,
            bg="#e6002e", fg="white", relief="flat",
            activebackground="#c90028", activeforeground="white"
        ).pack(fill="x", padx=8, pady=(0, 8), ipady=7)

        tk.Label(
            right, text="PLAYER", bg="#101010", fg="#bbbbbb",
            font=("Segoe UI", 9, "bold"), anchor="w"
        ).pack(fill="x", padx=10, pady=9)

        self.video_frame = tk.Frame(right, bg="#000000", height=300)
        self.video_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.video_frame.pack_propagate(False)

        controls = tk.Frame(right, bg="#101010")
        controls.pack(fill="x", padx=8, pady=(0, 8))

        tk.Button(
            controls, text="▶ Play", command=self.play_selected,
            bg="#252525", fg="white", relief="flat"
        ).pack(side="left", padx=(0, 5))
        tk.Button(
            controls, text="Ⅱ Pause", command=self.pause,
            bg="#252525", fg="white", relief="flat"
        ).pack(side="left", padx=5)
        tk.Button(
            controls, text="■ Stop", command=self.stop,
            bg="#252525", fg="white", relief="flat"
        ).pack(side="left", padx=5)

        self.volume = tk.IntVar(value=int(self.settings["volume"]))
        tk.Label(
            controls, text="Vol", bg="#101010", fg="#aaaaaa"
        ).pack(side="left", padx=(12, 3))
        tk.Scale(
            controls, from_=0, to=100, orient="horizontal",
            variable=self.volume, command=self.set_volume,
            bg="#101010", fg="white", troughcolor="#444444",
            highlightthickness=0, length=105
        ).pack(side="left")

        self.now_playing = tk.StringVar(value="Nothing playing")
        tk.Label(
            self.root, textvariable=self.now_playing,
            bg="#080808", fg="#bbbbbb", anchor="w",
            font=("Segoe UI", 9)
        ).pack(fill="x", padx=15, pady=(2, 9))

        tk.Label(
            self.root,
            text="YouTube Lite • Tkinter + MPV • Playback quality and FPS are best-effort",
            bg="#080808", fg="#555555", font=("Segoe UI", 8)
        ).pack(pady=(0, 7))

    def _init_player(self):
        try:
            folder = prepare_mpv_import()
            import mpv

            # Keep MPV conservative for a 2 GB RAM computer.
            self.video_frame.update_idletasks()
            hwnd = self.video_frame.winfo_id()
            self.player = mpv.MPV(
                wid=hwnd,
                config=False,
                osc=True,
                input_default_bindings=True,
                input_vo_keyboard=True,
                keep_open=True,
                idle=True,
                vo="gpu",
                hwdec=self.settings["hwdec"],
                ytdl=True,
                ytdl_format=self._format_for_quality(),
                cache=True,
                cache_secs=8,
                demuxer_max_bytes="40MiB",
                demuxer_max_back_bytes="8MiB",
            )
            self.player.volume = int(self.settings["volume"])
            self._apply_fps_filter()
            self.player_ready = True
            self.status.set("MPV player ready. Search for a video.")
        except Exception as exc:
            self.status.set("MPV setup required — see the setup instructions.")
            messagebox.showerror(
                "MPV could not start",
                str(exc) + "\n\nRead README.txt for MPV installation."
            )

    def _format_for_quality(self):
        q = self.settings["quality"]
        if q == "Best":
            return "bestvideo+bestaudio/best"
        return (
            f"bestvideo[height<={q}]+bestaudio/"
            f"best[height<={q}]/best"
        )

    def _apply_fps_filter(self):
        if not self.player:
            return
        try:
            if self.settings["fps"] == "30":
                self.player.command("vf", "set", "fps=fps=30")
            else:
                self.player.command("vf", "clr")
        except Exception:
            # Filter availability depends on the MPV build.
            self.status.set("Player ready; FPS filter unavailable in this MPV build.")

    def search(self):
        query = self.query.get().strip()
        if not query or self.search_busy:
            return
        self.search_busy = True
        self.search_button.configure(state="disabled")
        self.status.set("Searching YouTube...")
        self.listbox.delete(0, tk.END)
        self.results = []

        def worker():
            try:
                data = api_search(
                    self.settings["api_key"], query, self.kind.get()
                )
                self.root.after(0, lambda: self._show_results(data))
            except Exception as exc:
                msg = str(exc)
                self.root.after(0, lambda: self._search_error(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _show_results(self, data):
        self.results = data
        for item in data:
            prefix = "📁 " if item["kind"] == "playlist" else "▶ "
            self.listbox.insert(
                tk.END, prefix + item["title"] + "  —  " + item["channel"]
            )
        self.status.set(f"{len(data)} results found.")
        self.search_busy = False
        self.search_button.configure(state="normal")

    def _search_error(self, error):
        self.status.set("Search failed.")
        self.search_busy = False
        self.search_button.configure(state="normal")
        messagebox.showerror("YouTube search error", error)

    def play_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo("Select a result", "Choose a video or playlist first.")
            return
        item = self.results[selection[0]]
        if not self.player_ready or not self.player:
            messagebox.showerror(
                "MPV unavailable",
                "Install the MPV Windows 64-bit runtime and restart the app."
            )
            return

        if item["kind"] == "playlist":
            url = "https://www.youtube.com/playlist?list=" + item["id"]
        else:
            url = "https://www.youtube.com/watch?v=" + item["id"]

        try:
            self.player.ytdl_format = self._format_for_quality()
            self.player.play(url)
            self.now_playing.set("Playing: " + item["title"])
            self.status.set("Loading playback through MPV / yt-dlp...")
        except Exception as exc:
            messagebox.showerror("Playback error", str(exc))

    def pause(self):
        if self.player:
            try:
                self.player.pause = not self.player.pause
            except Exception:
                pass

    def stop(self):
        if self.player:
            try:
                self.player.stop()
                self.now_playing.set("Stopped")
            except Exception:
                pass

    def set_volume(self, value):
        if self.player:
            try:
                self.player.volume = int(float(value))
            except Exception:
                pass

    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("YouTube Lite Settings")
        win.configure(bg="#111111")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        pad = {"padx": 14, "pady": 6}
        tk.Label(
            win, text="SETTINGS", bg="#111111", fg="white",
            font=("Segoe UI", 14, "bold")
        ).pack(anchor="w", padx=14, pady=(14, 8))

        tk.Label(
            win, text="YouTube Data API v3 key",
            bg="#111111", fg="#cccccc"
        ).pack(anchor="w", **pad)
        key_var = tk.StringVar(value=self.settings["api_key"])
        key_entry = tk.Entry(
            win, textvariable=key_var, width=55, show="•",
            bg="#202020", fg="white", insertbackground="white",
            relief="flat"
        )
        key_entry.pack(fill="x", padx=14, ipady=7)

        show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            win, text="Show API key", variable=show_var,
            command=lambda: key_entry.configure(
                show="" if show_var.get() else "•"
            ),
            bg="#111111", fg="#cccccc", selectcolor="#222222",
            activebackground="#111111", activeforeground="white"
        ).pack(anchor="w", padx=14, pady=3)

        quality_var = tk.StringVar(value=self.settings["quality"])
        fps_var = tk.StringVar(value=self.settings["fps"])
        hw_var = tk.StringVar(value=self.settings["hwdec"])

        def option(label, variable, values):
            tk.Label(
                win, text=label, bg="#111111", fg="#cccccc"
            ).pack(anchor="w", **pad)
            box = ttk.Combobox(
                win, textvariable=variable, values=values,
                state="readonly", width=25
            )
            box.pack(anchor="w", padx=14)
            return box

        option("Maximum video quality", quality_var, ("360", "480", "720", "Best"))
        option("Frame-rate mode", fps_var, ("30", "60"))
        option("Hardware decoding", hw_var, ("auto-safe", "auto", "no"))

        tk.Label(
            win,
            text=("30 FPS applies an MPV frame filter where supported. "
                  "60 FPS clears that filter. Neither setting guarantees "
                  "the source's actual frame rate or performance."),
            bg="#111111", fg="#999999", wraplength=390,
            justify="left"
        ).pack(anchor="w", padx=14, pady=10)

        def save():
            self.settings.update({
                "api_key": key_var.get().strip(),
                "quality": quality_var.get(),
                "fps": fps_var.get(),
                "hwdec": hw_var.get(),
                "volume": int(self.volume.get()),
            })
            save_settings(self.settings)
            if self.player:
                try:
                    self.player.hwdec = self.settings["hwdec"]
                    self.player.ytdl_format = self._format_for_quality()
                    self._apply_fps_filter()
                except Exception:
                    pass
            self.status.set("Settings saved.")
            win.destroy()

        tk.Button(
            win, text="Save settings", command=save,
            bg="#e6002e", fg="white", relief="flat",
            padx=20, pady=8
        ).pack(pady=(4, 14))

    def close(self):
        self.closing = True
        try:
            if self.player:
                self.player.terminate()
        except Exception:
            pass
        self.root.destroy()

def main():
    root = tk.Tk()
    app = YouTubeLite(root)
    root.mainloop()

if __name__ == "__main__":
    main()
