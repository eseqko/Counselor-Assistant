@echo off
setlocal enabledelayedexpansion
title Counselor Assistant Installer
color 0B
echo.
echo  ============================================================
echo   COUNSELOR ASSISTANT - Installer for Windows
echo  ============================================================
echo.
echo   This will set up Counselor Assistant on your computer.
echo   All data stays local - nothing is uploaded to the cloud.
echo.
echo  ============================================================
echo.

REM --- Check for Python ---
set PYTHON=
where python >nul 2>&1 && set PYTHON=python && goto :check_version
where python3 >nul 2>&1 && set PYTHON=python3 && goto :check_version
where py >nul 2>&1 && set PYTHON=py && goto :check_version

echo  [ERROR] Python is not installed.
echo.
echo  Please install Python 3.9+ from:
echo    https://www.python.org/downloads/
echo.
echo  IMPORTANT: Check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:check_version
echo  [OK] Found Python: %PYTHON%
for /f "tokens=2" %%v in ('%PYTHON% --version 2^>^&1') do set PY_VER=%%v
echo       Version: %PY_VER%
echo.

REM --- Change to script directory ---
cd /d "%~dp0"

REM --- Create virtual environment if it doesn't exist ---
if not exist "venv" (
    echo  [1/4] Creating virtual environment...
    %PYTHON% -m venv venv
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to create virtual environment.
        echo  Try: %PYTHON% -m pip install virtualenv
        pause
        exit /b 1
    )
    echo        Done.
) else (
    echo  [1/4] Virtual environment already exists.
)
echo.

REM --- Activate venv ---
call venv\Scripts\activate.bat

REM --- Install dependencies ---
echo  [2/4] Installing dependencies...
pip install -r requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo  [ERROR] Failed to install dependencies.
    echo  Try running manually: pip install -r requirements.txt
    pause
    exit /b 1
)
echo        Done.
echo.

REM --- Create data directory ---
echo  [3/4] Setting up data directory...
if not exist "data" mkdir data
if not exist "data\backups" mkdir data\backups
if not exist "data\uploads" mkdir data\uploads
echo        Done.
echo.

REM --- Create desktop shortcut ---
echo  [4/4] Creating launcher...
(
echo @echo off
echo title Counselor Assistant
echo cd /d "%~dp0"
echo call venv\Scripts\activate.bat
echo python run.py
echo pause
) > "start.bat"

REM --- Create desktop shortcut if possible ---
set SHORTCUT=%USERPROFILE%\Desktop\Counselor Assistant.bat
(
echo @echo off
echo title Counselor Assistant
echo cd /d "%~dp0"
echo call venv\Scripts\activate.bat
echo start http://127.0.0.1:5000
echo python run.py
) > "%SHORTCUT%" 2>nul
if exist "%SHORTCUT%" (
    echo        Created desktop shortcut.
) else (
    echo        Desktop shortcut skipped (no permissions).
)
echo.

echo  ============================================================
echo   INSTALLATION COMPLETE
echo  ============================================================
echo.
echo   To start Counselor Assistant:
echo     1. Double-click "start.bat" in this folder
echo        (or the shortcut on your Desktop)
echo     2. Open http://127.0.0.1:5000 in your browser
echo.
echo   First-time setup:
echo     The app will guide you through initial configuration.
echo.
echo   Your data is stored in: %cd%\data\
echo   Back up this folder regularly!
echo.
echo  ============================================================
echo.
echo  ============================================================
echo   BEFORE YOU ADD REAL STUDENT DATA
echo  ============================================================
echo   Student records are stored in plain files on this PC.
echo   The app login does NOT protect them if the laptop is lost
echo   or the drive is read from another operating system.
echo.
echo   Turn on BitLocker now:
echo     Settings ^> Privacy ^& security ^> Device encryption
echo.
echo   On an unencrypted laptop, a loss is a reportable FERPA
echo   breach. This is a prerequisite, not a suggestion.
echo  ============================================================
echo.
set /p LAUNCH="  Launch now? (Y/n): "
if /i "%LAUNCH%"=="n" goto :done
if /i "%LAUNCH%"=="N" goto :done

echo.
echo  Starting Counselor Assistant...
start http://127.0.0.1:5000
python run.py

:done
pause
