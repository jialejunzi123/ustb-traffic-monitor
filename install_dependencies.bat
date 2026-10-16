@echo off
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m pip install -r "%~dp0requirements.txt"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python was not found. Install Python 3.10 or newer first.
        pause
        exit /b 1
    )
    python -m pip install -r "%~dp0requirements.txt"
)
if errorlevel 1 (
    echo Dependency installation failed. Check your network or Python pip setup.
    pause
    exit /b 1
)
echo Dependencies installed. You can now run start_widget.bat.
pause
