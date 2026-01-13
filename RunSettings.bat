@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
start "" pythonw settings.py
exit
