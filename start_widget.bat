@echo off
cd /d "%~dp0"
set "SE_AVOID_STATS=true"
set "SE_CACHE_PATH=%~dp0.selenium_cache"
where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3 "%~dp0campus_traffic_widget.py"
    exit /b
)
where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0campus_traffic_widget.py"
    exit /b
)
echo Python for Windows with tkinter was not found. Install Python and try again.
pause
