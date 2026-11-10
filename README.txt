YOUTUBE LITE 1.0.0
Lightweight, portable YouTube desktop client for old, low-memory PCs
(designed around: Intel Celeron 847, 1.1 GHz, 2 GB RAM, Intel HD Graphics, Windows 10)

WHAT IT IS
  A native Python/Qt (PySide6 Widgets) program. It searches YouTube with yt-dlp
  and plays videos in a separate mpv process. No browser engine is bundled.
  No account, no login, no telemetry. Everything is stored in this folder.

IMPORTANT REQUIREMENTS
  * 64-BIT Windows 10. The Qt GUI (PySide6) does not exist for 32-bit Windows.
    Many 2011 laptops with 2 GB RAM were set up with 32-bit Windows. Check:
    Settings > System > About > "System type". If it says 32-bit, this program
    cannot run on that install (reinstalling 64-bit Windows 10 is possible on
    a Celeron 847, which is a 64-bit CPU, but 2 GB is tight).
  * mpv.exe in the "mpv" folder (see "Getting mpv"). Use the standard x86_64
    build, NOT an "x86_64-v3" / AVX2 build: a Celeron 847 has no AVX/AVX2.
  * runtime\deno.exe: the JavaScript runtime YouTube now requires (the GitHub
    build bundles it; if you build by hand, copy deno.exe from
    https://github.com/denoland/deno/releases into the "runtime" folder).
  * Internet connection.

FIRST RUN
  1. Extract the folder anywhere (a USB drive is fine). No installer, no admin.
  2. Make sure mpv\mpv.exe exists.
  3. Run YouTube-Lite.exe.
  4. Type a search and press Enter. Nothing loads before you search.

GETTING MPV
  Download a Windows build of mpv from https://mpv.io/installation/ (Windows
  builds section), extract it, and copy mpv.exe (and any DLLs/folders that came
  with it) into the "mpv" folder next to YouTube-Lite.exe. Pick the plain
  x86_64 build (not -v3). The "mpv.conf" in that folder holds conservative
  settings; options your mpv build does not know are skipped automatically.

USING IT
  Header: search box, performance mode (ECO / BALANCED / QUALITY, switch any
  time), ad-blocker indicator, settings.
  Click a video: the stream information is read (nothing is downloaded), then
  mpv opens at the default quality (ECO: 360p). On the player page you can pick
  another quality (144p-1080p where YouTube offers it) and press "Open player";
  playback resumes at the current position.
  mpv has its own on-screen controls (play/pause, seek, volume, fullscreen,
  speed). The player page also has buttons for the common ones.
  Sidebar: Home (recently played), Search, Trending (topic searches),
  Subscriptions (channels you save locally), History, Watch Later, Playlists,
  Settings. Use the "..." button on a card for more actions.

PERFORMANCE MODES
  ECO (default)  10 results/page, small thumbnails, 360p default, minimal cache.
  BALANCED       15 results/page, normal thumbnails, moderate cache.
  QUALITY        20 results/page, larger thumbnails, more cache, extra metadata.

QUALITY ON THIS LAPTOP (honest expectations)
  Resolution being AVAILABLE does not mean it will play SMOOTHLY.
  * 240p/360p/480p: expected to be fine.
  * 720p H.264 at 24-30 fps: the main high-quality target. It may work if the
    Intel HD Graphics decodes H.264 in hardware (mpv must report it; the player
    page shows "decoding: hardware (...)" or "software" as measured by mpv).
  * 1080p: experimental. Do not expect smooth playback without testing.
  * VP9 / AV1 / HEVC: not hardware-decoded by this generation; avoided by
    default (H.264 is preferred). The quality table says when no H.264 exists.
  If frames are dropped or decoding is software, the player page recommends a
  lower resolution.
  Measured numbers for the real machine are in PERFORMANCE_REPORT.md; values
  that have not been measured are marked as such.

WEB MODE
  "Open in browser (Web Mode)" opens the video on youtube.com in YOUR browser,
  only when you click it. Browsers can use several hundred MB of RAM. The native
  player does not depend on it, and it is not the full YouTube website.

AD / TRACKER BLOCKER (optional, default OFF)
  Controls: thumbnail downloads made by YouTube Lite and a host check on
  stream addresses before they go to mpv or your browser.
  Does NOT control: anything mpv or your browser requests afterwards, or ads
  served from the same servers as the video. It does not modify the Windows
  hosts file, firewall or browsers, never installs extensions and never touches
  sign-in. YouTube/Google playback domains are protected. Do not expect
  universal ad removal. Lists: filters\blocklist.txt, filters\allowlist.txt,
  plus an optional list you download manually (Settings > Ad blocker).

PRIVACY AND SECURITY
  No telemetry, no account, no Google password, no cookies. Network requests go
  only to YouTube (via yt-dlp), YouTube image servers (thumbnails), and the
  filter-list address if YOU press "Update filter list". HTTPS only, with
  timeouts. mpv is started with an argument list (never through a shell).
  Downloaded filter lists are parsed as plain domain names, never executed.
  History, playlists and settings stay in this folder. Settings > Storage has
  buttons to clear everything.

UNINSTALL
  Close YouTube Lite, then run Uninstall-YouTube-Lite.bat (inside the folder).
  It asks for confirmation and deletes the whole folder. Or just delete the
  folder yourself: nothing else is installed on the computer.

FOLDERS (portable)
  YouTube-Lite.exe        the program   (plus a "_internal" folder with its libraries)
  config\settings.json    settings
  data\history.db         history, watch later, playlists, saved channels
  cache\thumbnails, cache\metadata   size-limited caches (defaults 30 MB / 5 MB)
  filters\                blocklist.txt, allowlist.txt, downloaded.txt
  mpv\                    mpv.exe, mpv.conf
  runtime\                deno.exe (needed by yt-dlp for YouTube)
  logs\                   small rotating log (default max 2 MB)
  Nothing is written to the registry, AppData, or anywhere outside this folder.

LIMITS OF THIS VERSION
  * Live streams and premieres are not supported (use Web Mode).
  * No sign-in: no private videos, age-restricted videos, members-only content,
    or your real YouTube subscriptions/playlists.
  * YouTube's own Trending feed is not available through yt-dlp; the Trending
    page runs ordinary topic searches.
  * Channel search uses YouTube's website search filter through yt-dlp and may
    break when YouTube changes.
  * YouTube changes often. When searching/playing stops working, yt-dlp must be
    updated by rebuilding (see TROUBLESHOOTING.txt).

BUILDING FROM SOURCE
  Install 64-bit Python 3.9+, then run build_windows.bat. For development run
  run_dev.bat. Put mpv in third_party\mpv before building to have it copied in.

YouTube Lite is an independent project, not affiliated with or endorsed by
YouTube or Google. Respect YouTube's Terms of Service. See LICENSES.txt.
