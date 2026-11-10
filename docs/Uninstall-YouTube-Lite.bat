@echo off
setlocal
cd /d "%~dp0"
if not exist "YouTube-Lite.exe" (
  echo This file must stay inside the YouTube-Lite folder, next to YouTube-Lite.exe.
  pause
  exit /b 1
)
if "%CD%"=="%CD:~0,3%" (
  echo Refusing to run: YouTube Lite is in the root of a drive. Move it into its own folder first.
  pause
  exit /b 1
)
echo ============================================================
echo  Uninstall YouTube Lite
echo ============================================================
echo This will PERMANENTLY DELETE this folder and everything in it:
echo   %CD%
echo including your settings, history, playlists and cache.
echo Nothing else on this computer was changed by YouTube Lite
echo (it never writes to the registry or other folders).
echo.
set /p ANS=Type YES and press Enter to continue: 
if /i not "%ANS%"=="YES" (
  echo Cancelled. Nothing was deleted.
  pause
  exit /b 0
)
taskkill /f /im YouTube-Lite.exe >nul 2>nul
set "TARGET=%CD%"
cd /d "%TEMP%"
> "%TEMP%\ytlite_rm.bat" echo @echo off
>> "%TEMP%\ytlite_rm.bat" echo ping -n 3 127.0.0.1 ^>nul
>> "%TEMP%\ytlite_rm.bat" echo rmdir /s /q "%TARGET%"
>> "%TEMP%\ytlite_rm.bat" echo del "%%~f0"
start "" /min "%TEMP%\ytlite_rm.bat"
echo YouTube Lite is being removed. You can close this window.
exit /b 0
