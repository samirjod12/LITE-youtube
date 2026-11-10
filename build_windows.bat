@echo off
setlocal enableextensions
rem ============================================================
rem  YouTube Lite - Windows portable build (PyInstaller, one-folder)
rem  Output: dist\YouTube-Lite\YouTube-Lite.exe  (+ portable folders)
rem  Needs: 64-bit Python 3.9+ and an internet connection for pip.
rem ============================================================
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
  echo [ERROR] Python 3 was not found. Install 64-bit Python from python.org ^(tick "Add to PATH"^).
  exit /b 1
)

echo [1/7] Checking Python...
%PY% -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.9 or newer is required.
  exit /b 1
)
%PY% -c "import struct,sys; sys.exit(0 if struct.calcsize('P')==8 else 1)"
if errorlevel 1 (
  echo [ERROR] This is 32-bit Python. PySide6 only exists for 64-bit Windows. Install 64-bit Python.
  exit /b 1
)

echo [2/7] Creating build environment (.venv-build)...
if not exist ".venv-build\Scripts\python.exe" (
  %PY% -m venv .venv-build
  if errorlevel 1 ( echo [ERROR] Could not create the virtual environment. & exit /b 1 )
)
set VPY=.venv-build\Scripts\python.exe

echo [3/7] Checking / installing dependencies...
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency installation failed. Check your internet connection.
  exit /b 1
)
"%VPY%" -c "import PySide6, yt_dlp, PyInstaller; print('PySide6', PySide6.__version__, '| yt-dlp', yt_dlp.version.__version__, '| PyInstaller', PyInstaller.__version__)"
if errorlevel 1 ( echo [ERROR] A dependency did not import. & exit /b 1 )

echo [4/7] Running unit tests...
"%VPY%" -m unittest discover -s tests -v
if errorlevel 1 (
  echo [ERROR] Unit tests failed. Build stopped.
  exit /b 1
)

if not exist assets\icon.ico "%VPY%" tools\make_icon.py assets\icon.ico
echo [5/7] Building the executable...
if exist build rmdir /s /q build
if exist dist\YouTube-Lite rmdir /s /q dist\YouTube-Lite
"%VPY%" -m PyInstaller --noconfirm --clean --onedir --windowed --noupx ^
  --name YouTube-Lite --paths src --icon assets\icon.ico ^
  --collect-submodules yt_dlp --collect-all yt_dlp_ejs ^
  --exclude-module tkinter ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtWebEngineQuick --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQuickWidgets ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtMultimedia ^
  --exclude-module PySide6.QtMultimediaWidgets --exclude-module PySide6.QtSql ^
  --exclude-module PySide6.QtPdf --exclude-module PySide6.QtCharts ^
  --exclude-module PySide6.QtDataVisualization --exclude-module PySide6.QtBluetooth ^
  --exclude-module PySide6.QtSerialPort --exclude-module PySide6.QtSensors ^
  main.py
if errorlevel 1 (
  echo [ERROR] PyInstaller failed. See the messages above.
  exit /b 1
)
if not exist dist\YouTube-Lite\YouTube-Lite.exe (
  echo [ERROR] YouTube-Lite.exe was not produced.
  exit /b 1
)

echo [6/7] Assembling the portable folder...
set OUT=dist\YouTube-Lite
for %%D in (config data cache\thumbnails cache\metadata filters mpv logs) do (
  if not exist "%OUT%\%%D" mkdir "%OUT%\%%D"
)
copy /y filters\blocklist.txt "%OUT%\filters\" >nul
copy /y filters\allowlist.txt "%OUT%\filters\" >nul
copy /y mpv\mpv.conf "%OUT%\mpv\" >nul
copy /y README.txt "%OUT%\" >nul
copy /y LICENSES.txt "%OUT%\" >nul
copy /y docs\USB_GUIDE.txt "%OUT%\" >nul
copy /y docs\TROUBLESHOOTING.txt "%OUT%\" >nul
copy /y docs\Uninstall-YouTube-Lite.bat "%OUT%\" >nul
copy /y docs\PERFORMANCE_REPORT.md "%OUT%\" >nul

echo [7/7] Packaging mpv and the JavaScript runtime...
if exist third_party\runtime\deno.exe (
  if not exist "%OUT%\runtime" mkdir "%OUT%\runtime"
  copy /y third_party\runtime\deno.exe "%OUT%\runtime\" >nul
  echo     deno copied into %OUT%\runtime
) else (
  echo [WARNING] third_party\runtime\deno.exe not found. YouTube may refuse to play videos until
  echo           deno.exe is placed in %OUT%\runtime\  ^(see README.txt^).
)
if exist third_party\mpv\mpv.exe (
  xcopy /e /i /y third_party\mpv\* "%OUT%\mpv\" >nul
  echo     mpv copied into %OUT%\mpv
) else (
  echo [WARNING] third_party\mpv\mpv.exe not found. The app was built, but PLAYBACK WILL NOT WORK
  echo           until mpv.exe is placed in %OUT%\mpv\  ^(see README.txt, section "Getting mpv"^).
)

echo.
echo Build finished: %OUT%\YouTube-Lite.exe
echo NOTE: a successful build is not a tested build. Run the checklist in PERFORMANCE_REPORT.md.
exit /b 0
