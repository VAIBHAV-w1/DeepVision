@echo off
title DeepVision Docker Setup
cd /d "%~dp0"

echo ========================================
echo  DeepVision One-Shot Docker Setup
echo ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_deepvision.ps1" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Setup script exited with error code %ERRORLEVEL%.
    echo Please see messages above for troubleshooting.
    echo.
    pause
) else (
    echo.
    pause
)
