@echo off
cd /d "%~dp0.."
set /p SLUG="Enter slug (add --movie at the end for movies): "
if "%SLUG%"=="" (
    echo No slug entered.
    pause
    exit /b
)
python main.py lookup %SLUG%
pause
