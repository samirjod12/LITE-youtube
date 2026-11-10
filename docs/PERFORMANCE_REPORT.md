# YouTube Lite 1.0.0 — Test and Performance Report

**Status: the benchmark sections are NOT MEASURED.** No Intel Celeron 847 machine, Windows,
mpv, network access or real PySide6 was available when the code was written. No number in
this document is invented. "Not run" means exactly that. Fill the tables in on the real laptop.

## 1. What was verified (development sandbox, Linux, Python 3.13, no network)

| Check | Method | Result |
|---|---|---|
| Core logic: config/profiles, SQLite storage, caches, ad-blocker rules, error classification, format selection, mpv command building, IPC protocol, playback-health rules, mpv.conf validation, hardware-generation hints | `python -m unittest discover -s tests` (66 tests) | passed |
| GUI wiring (window construction, all pages, search → grid, pagination, widget reuse, cache hit, live profile switch, play → quality table → mpv launch call, history/watch later/playlists, cache clearing, portable folder creation) | `python tests/stub_smoke.py` — executes the GUI code against a **fake Qt and fake yt-dlp** (30 checks) | passed |

Limits of that evidence: the stub run proves the code is internally consistent. It does **not**
prove real Qt layout/painting, real threading, real YouTube extraction, real mpv playback, the
Windows job-object/IPC pipe code, or PyInstaller packaging. Treat those as **untested**.

## 2. Test matrix (run on the target laptop)

Legend: ✅ verified here · ⬜ not run (needs real environment)

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Application startup | ⬜ | stub-constructed only |
| 2 | Home interface | ⬜ | |
| 3 | YouTube search | ⬜ | needs network + real yt-dlp |
| 4 | Search pagination | ⬜ | request ranges (1-10, 11-20) checked against fake yt-dlp ✅ |
| 5 | Thumbnail loading | ⬜ | |
| 6 | Video extraction | ⬜ | format selection logic ✅ (fake data) |
| 7 | mpv launching | ⬜ | command line ✅ (unit-tested), process start ⬜ |
| 8 | Playback shutdown / no orphan mpv | ⬜ | |
| 9 | 240p playback | ⬜ | |
| 10 | 360p playback | ⬜ | |
| 11 | 480p playback | ⬜ | |
| 12 | 720p H.264 playback | ⬜ | primary high-quality target |
| 13 | 1080p H.264 playback | ⬜ | experimental |
| 14 | Hardware decoding (mpv `hwdec-current`) | ⬜ | |
| 15 | Software decoding | ⬜ | |
| 16 | ECO mode | ⬜ | settings/limits ✅ (unit), runtime behaviour ⬜ |
| 17 | Ad blocker toggle | ⬜ | rule logic ✅ (unit) |
| 18 | Search history | ✅ | storage logic (unit) |
| 19 | Playlist storage | ✅ | storage logic (unit) |
| 20 | Cache cleanup / size limit | ✅ | logic (unit) |
| 21 | Portable folder operation | ⬜ | folder creation ✅ (unit); built .exe ⬜ |
| 22 | USB operation / unplug handling | ⬜ | |
| 23 | Repeated searches (leak check) | ⬜ | |
| 24 | Memory consumption | ⬜ | see below |

## 3. How to measure on the real laptop

1. Use a Windows 10 **64-bit** install, ECO mode, nothing else running. Note the Windows build,
   Intel graphics driver version (Settings > Playback > Detect hardware) and mpv version.
2. Memory: `python tools/measure_memory.py --name YouTube-Lite.exe --seconds 60 --label idle`
   (add `--name mpv.exe` to include the player). Scenarios: idle after start; during a search;
   after 20 consecutive searches (leak check); playing each quality.
   Settings > About > "Measure memory now" gives a quick reading.
3. CPU: Task Manager > Details, or `typeperf "\Process(mpv)\% Processor Time" -sc 30`
   (divide by the 2 cores as appropriate and say which you report).
4. Dropped frames and decoding mode: the player page's live line (values measured by mpv:
   `frame-drop-count`, `decoder-frame-drop-count`, `hwdec-current`). Play at least 2 minutes per quality.
5. Startup time: stopwatch from double-click to usable window (cold and warm), HDD and USB.

## 4. Results (fill in)

Hardware: Intel Celeron 847 / 2 GB DDR3 / Intel HD Graphics (driver: ______) / Windows 10 ____ (64-bit)

| Metric | ECO | Balanced | Quality |
|---|---|---|---|
| Idle RAM (YouTube-Lite.exe, working set / private) | NOT MEASURED | NOT MEASURED | NOT MEASURED |
| RAM while searching | NOT MEASURED | NOT MEASURED | NOT MEASURED |
| RAM after 20 searches | NOT MEASURED | NOT MEASURED | NOT MEASURED |
| Startup time | NOT MEASURED | – | – |
| Cache size after 20 searches | NOT MEASURED | NOT MEASURED | NOT MEASURED |

| Playback | Decoding (measured) | CPU % | RAM mpv | Dropped frames | Verdict |
|---|---|---|---|---|---|
| 240p | NOT MEASURED | | | | |
| 360p | NOT MEASURED | | | | |
| 480p | NOT MEASURED | | | | |
| 720p H.264 | NOT MEASURED | | | | |
| 1080p H.264 | NOT MEASURED | | | | |

Design targets (goals, not results): 100–200 MB idle RAM, minimal idle CPU, no memory growth.
Design choices that serve them: lazy yt-dlp import, reused card widgets, thumbnails loaded only when
visible, one network worker thread, no timers while idle (the player status timer exists only while
mpv runs), size-limited caches, mpv cache limited to 15 s / 48 MiB.

## 5. Expected behaviour (reasoned, NOT measured)

* Intel HD Graphics from a Celeron 847 (Sandy Bridge generation) is expected to decode H.264 in
  hardware and **not** VP9/AV1/HEVC. This is a hint from the CPU generation; the real answer is
  mpv's `hwdec-current` while playing, shown on the player page.
* If H.264 decodes in hardware, 360p–720p may be smooth; 1080p remains uncertain.
* In software, 720p+ is likely to drop frames on a 1.1 GHz dual-core.

## 6. Known limitations

* Untested: real Qt/PySide6 run, Windows named-pipe IPC, job-object cleanup, PyInstaller build,
  real YouTube extraction (YouTube changes often), channel search filter, real mpv option set.
* PySide6 requires 64-bit Windows; 32-bit Windows 10 installs cannot run this app.
* No live streams, no sign-in, no YouTube-account features, no Trending feed (topic searches instead).
* The ad blocker cannot affect traffic made by mpv or the browser.
* yt-dlp must be refreshed by rebuilding when YouTube breaks extraction.
