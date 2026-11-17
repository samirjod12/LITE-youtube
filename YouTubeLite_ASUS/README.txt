YOUTUBE LITE — ASUS EDITION
============================

Target:
- Windows 10 64-bit
- 2 GB RAM (700 MB free at the time of design)
- Python + Tkinter UI
- MPV/libmpv playback engine
- yt-dlp via MPV's ytdl_hook
- YouTube Data API v3 search for videos and playlists

IMPORTANT REALITY CHECK
-----------------------
This is a source project, not a precompiled EXE.
It does not bundle Python, MPV, WebView2, or a browser.
MPV hardware decoding depends on your graphics driver and codec support.
The 30 FPS option uses MPV's fps video filter when supported. It can drop
or duplicate frames, but cannot guarantee smooth 30 FPS on old hardware.
The 60 FPS option clears that filter; it does not force a 60 FPS stream.

1. INSTALL PYTHON
-----------------
Install Python 3.11.x 64-bit:
https://www.python.org/downloads/release/python-3119/

During setup:
- Check "Add python.exe to PATH".
- Install pip.
- Tkinter is included with the standard Windows installer.

2. INSTALL MPV
--------------
Download a 64-bit Windows MPV build from the MPV project/community builds:
https://mpv.io/installation/

Extract the archive. Find the folder containing mpv-2.dll or libmpv-2.dll.
Create a folder named "mpv" beside youtube_lite.py and copy the DLL and
the MPV runtime files needed by that build into it. Keep the MPV scripts
folder if included (MPV's ytdl_hook script is needed).

The app searches:
- .\mpv\
- the application folder
- C:\mpv
- C:\Program Files\mpv
- MPV_HOME environment variable

If your build names the library libmpv-2.dll, the app accepts that too.
Some builds need additional DLLs from the same archive. Keep those files
together in the mpv folder.

3. INSTALL PYTHON PACKAGES
--------------------------
Open Command Prompt in this project folder and run:

    python -m pip install --no-cache-dir python-mpv yt-dlp

MPV's ytdl_hook must be able to find yt-dlp.exe. The app adds the Python
Scripts directory to PATH if yt-dlp is discoverable there.

4. GET YOUR OWN YOUTUBE API KEY
-------------------------------
A. Open https://console.cloud.google.com/
B. Create a project.
C. Enable YouTube Data API v3:
   https://console.cloud.google.com/apis/library/youtube.googleapis.com
D. Create an API key:
   https://console.cloud.google.com/apis/credentials
E. Restrict the key to YouTube Data API v3.
F. Open YouTube Lite > Settings and paste the key.

Do not publish your API key in public source repositories. The app stores
the key locally in:
    %APPDATA%\YouTubeLite\settings.json

5. RUN
------
From Command Prompt:

    python youtube_lite.py

6. LOW-MEMORY TIPS
------------------
- Close other browser tabs and unnecessary applications.
- Start at 360p.
- Try hardware decoding "auto-safe".
- If video is corrupted or crashes, change hardware decoding to "no".
- If playback stutters, try 480p only if the laptop can handle it.
- Avoid running multiple instances.
- Keep Windows page-file/system-managed virtual memory enabled.
- The player uses a small MPV cache; network buffering still varies.

7. TROUBLESHOOTING
------------------
"MPV DLL not found":
- Check that mpv-2.dll or libmpv-2.dll is in the mpv folder beside the
  Python file.
- Keep dependent DLLs from the same MPV archive in that folder.
- Ensure both Python and MPV are 64-bit.

"yt-dlp not found" / YouTube extraction fails:
    python -m pip install --upgrade yt-dlp

"API key not valid":
- Confirm YouTube Data API v3 is enabled.
- Check that the API key restriction allows YouTube Data API v3.
- Check quota and Google Cloud project.

"Video playback fails":
- Update yt-dlp.
- Check whether MPV's ytdl_hook.lua script is present in the MPV scripts
  directory in your build.
- Some videos may be age-restricted, private, region-restricted, or
  otherwise unavailable to third-party players.

NOTES
-----
- Search uses the official YouTube Data API.
- Playback resolution uses yt-dlp and MPV, not the Data API.
- This app does not download video files.
- Use the player in accordance with YouTube's terms and applicable law.
- YouTube API quota and terms apply.
