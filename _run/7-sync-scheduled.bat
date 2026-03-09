@echo off
cd /d "%~dp0.."
python main.py sync --schedule 6h
pause
