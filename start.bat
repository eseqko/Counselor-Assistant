@echo off
title Counselor Assistant
cd /d "%~dp0"

REM --- Use virtual environment if available ---
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    REM --- Find Python ---
    where python >nul 2>&1 && set PYTHON=python && goto :run
    where python3 >nul 2>&1 && set PYTHON=python3 && goto :run
    where py >nul 2>&1 && set PYTHON=py && goto :run
    echo  Python not found. Run install.bat first.
    pause
    exit /b 1
)
set PYTHON=python

:run
REM --- Check if dependencies are installed ---
%PYTHON% -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo  Installing dependencies (first-time setup)...
    %PYTHON% -m pip install -r requirements.txt --quiet
)

echo.
echo  Starting Counselor Assistant...
echo  Open: http://127.0.0.1:5000
echo  Press Ctrl+C to stop.
echo.
%PYTHON% run.py
pause
