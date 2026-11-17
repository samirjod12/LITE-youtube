@echo off
cd /d "%~dp0"
python youtube_lite.py
if errorlevel 1 pause
