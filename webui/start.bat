@echo off
cd /d "%~dp0"
echo Starting RSS WebUI...
echo.
python server.py
pause