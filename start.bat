@echo off
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Run install.py first:  python install.py
    pause
    exit /b 1
)
venv\Scripts\python.exe run_dashboard.py
