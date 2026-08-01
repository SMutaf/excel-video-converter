@echo off
rem Launches the desktop application without a console window.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m excelvid.gui
