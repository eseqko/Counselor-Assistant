@echo off
title Counselor Assistant
echo.
echo ============================================================
echo   COUNSELOR ASSISTANT - Starting Up...
echo ============================================================
echo.

REM --- Find Python ---
where python >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python
    goto :found_python
)
where python3 >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python3
    goto :found_python
)
where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=py
    goto :found_python
)

echo  ERROR: Python is not installed or not in your PATH.
echo.
echo  Please install Python 3.10+ from https://www.python.org/downloads/
echo  IMPORTANT: Check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:found_python
echo  Found Python: %PYTHON%
%PYTHON% --version
echo.

REM --- Change to the directory where this .bat file lives ---
cd /d "%~dp0"

REM --- Install dependencies if needed ---
%PYTHON% -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo  Installing dependencies (first-time setup)...
    echo.
    %PYTHON% -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo.
        echo  ERROR: Failed to install dependencies.
        echo  Try running manually: %PYTHON% -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
    echo.
    echo  Dependencies installed successfully!
    echo.
)

REM --- Launch the app ---
echo  Starting Counselor Assistant...
echo  (This window must stay open while the app is running)
echo.
%PYTHON% run.py
if %errorlevel% neq 0 (
    echo.
    echo  ============================================================
    echo   The application exited with an error.
    echo   Check the messages above for details.
    echo  ============================================================
    echo.
)
pause
