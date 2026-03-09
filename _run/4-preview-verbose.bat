@echo off
cd /d "%~dp0.."
git pull origin main
python main.py sync --dry-run --verbose
pause
