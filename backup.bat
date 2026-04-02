@echo off
title Counselor Assistant - Backup
cd /d "%~dp0"

REM ============================================================
REM  Backup data to network folder
REM  Edit the NETWORK_PATH below if your folder location changes
REM ============================================================
set NETWORK_PATH=\\store\staff$\jvillalobos\Data

echo.
echo  Counselor Assistant - Backup
echo  Destination: %NETWORK_PATH%
echo.

REM --- Check network folder is reachable ---
if not exist "%NETWORK_PATH%" (
    echo  ERROR: Cannot reach %NETWORK_PATH%
    echo  Make sure you are connected to the school network.
    echo.
    pause
    exit /b 1
)

REM --- Create subfolder on network ---
if not exist "%NETWORK_PATH%\CounselorBackup" mkdir "%NETWORK_PATH%\CounselorBackup"

REM --- Copy database ---
if exist "data\counselor.db" (
    copy /y "data\counselor.db" "%NETWORK_PATH%\CounselorBackup\counselor.db" >nul
    echo  Database backed up.
) else (
    echo  No database found — nothing to back up.
    pause
    exit /b 1
)

REM --- Copy uploads folder ---
if exist "data\uploads" (
    xcopy /s /e /y /i "data\uploads" "%NETWORK_PATH%\CounselorBackup\uploads" >nul
    echo  Uploads folder backed up.
)

REM --- Timestamp ---
echo %date% %time% > "%NETWORK_PATH%\CounselorBackup\last_backup.txt"

echo.
echo  Backup complete!
echo  Location: %NETWORK_PATH%\CounselorBackup
echo.
pause
