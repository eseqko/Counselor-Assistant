@echo off
title Counselor Assistant - Restore
cd /d "%~dp0"

REM ============================================================
REM  Restore data from network folder
REM  Edit the NETWORK_PATH below if your folder location changes
REM ============================================================
set NETWORK_PATH=\\store\staff$\jvillalobos\Data

echo.
echo  Counselor Assistant - Restore
echo  Source: %NETWORK_PATH%\CounselorBackup
echo.

REM --- Check network folder is reachable ---
if not exist "%NETWORK_PATH%\CounselorBackup\counselor.db" (
    echo  ERROR: No backup found at %NETWORK_PATH%\CounselorBackup
    echo  Run backup.bat on your other PC first.
    echo.
    pause
    exit /b 1
)

REM --- Show last backup time ---
if exist "%NETWORK_PATH%\CounselorBackup\last_backup.txt" (
    set /p LAST_BACKUP=<"%NETWORK_PATH%\CounselorBackup\last_backup.txt"
    echo  Last backup: %LAST_BACKUP%
)

REM --- Confirm before overwriting ---
echo.
echo  WARNING: This will replace your LOCAL data with the network copy.
echo  If you have local changes you haven't backed up, they will be lost.
echo.
set /p CONFIRM=Type YES to continue:
if /i not "%CONFIRM%"=="YES" (
    echo  Restore cancelled.
    pause
    exit /b 0
)

REM --- Ensure data folder exists ---
if not exist "data" mkdir "data"

REM --- Copy database ---
copy /y "%NETWORK_PATH%\CounselorBackup\counselor.db" "data\counselor.db" >nul
echo  Database restored.

REM --- Copy uploads ---
if exist "%NETWORK_PATH%\CounselorBackup\uploads" (
    xcopy /s /e /y /i "%NETWORK_PATH%\CounselorBackup\uploads" "data\uploads" >nul
    echo  Uploads folder restored.
)

echo.
echo  Restore complete! You can now run start.bat.
echo.
pause
