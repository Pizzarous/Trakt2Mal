@echo off
cd /d "%~dp0.."
python main.py sync --dry-run
pause
