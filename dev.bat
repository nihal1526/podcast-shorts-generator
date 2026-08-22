@echo off
REM Windows 1-Click Runner for Podcast Shorts Studio
title Podcast Shorts Studio

echo ========================================================
echo   Launching Podcast Shorts Studio...
echo ========================================================

IF EXIST ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" dev.py %*
) ELSE (
    python dev.py %*
)

pause
