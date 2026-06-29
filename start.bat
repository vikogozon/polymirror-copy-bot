@echo off
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Run install.py first:  python install.py
    pause
    exit /b 1
)
venv\Scripts\python.exe run_dashboard.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] The bot exited with an error. See message above.
    pause
)
