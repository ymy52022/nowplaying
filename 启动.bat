@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setup missing - run install.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" listen.py
pause
