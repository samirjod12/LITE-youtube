@echo off
rem YouTube Lite - run from source (development). Needs 64-bit Python 3.9+.
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
  echo Python 3 was not found. Install 64-bit Python from python.org and tick "Add to PATH".
  pause
  exit /b 1
)
%PY% -c "import PySide6, yt_dlp" >nul 2>nul
if errorlevel 1 (
  echo Installing runtime packages ^(PySide6, yt-dlp^) for the current user...
  %PY% -m pip install --user PySide6 yt-dlp
  if errorlevel 1 (
    echo Package installation failed. Check your internet connection.
    pause
    exit /b 1
  )
)
%PY% main.py
if errorlevel 1 pause
