@echo off
REM Build script for vtg_image_util
REM Creates both CLI and GUI executables
REM Requires: pip install pyinstaller wxpython

setlocal enabledelayedexpansion

echo =============================================
echo Victor 9000 Disk Image Utility - Build Script
echo =============================================
echo.

REM Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller
        exit /b 1
    )
)

REM Get version from package
for /f "tokens=2 delims==" %%v in ('python -c "from vtg_image_util import __version__; print(__version__)"') do set VERSION=%%v
if "%VERSION%"=="" set VERSION=1.0.0

echo Building version: %VERSION%
echo.

REM Clean previous builds
echo Cleaning previous builds...
if exist "dist\vtg_image_util.exe" del "dist\vtg_image_util.exe"
if exist "dist\vtg_image_util_gui.exe" del "dist\vtg_image_util_gui.exe"
if exist "build" rmdir /s /q "build"

REM Build using the spec file
echo.
echo Building executables...
pyinstaller --clean vtg_image_util.spec

if errorlevel 1 (
    echo.
    echo Build failed!
    exit /b 1
)

REM Check results
echo.
echo =============================================
echo Build Results:
echo =============================================

if exist "dist\vtg_image_util.exe" (
    echo [OK] CLI:  dist\vtg_image_util.exe
    for %%A in ("dist\vtg_image_util.exe") do echo       Size: %%~zA bytes
) else (
    echo [FAIL] CLI executable not created
)

if exist "dist\vtg_image_util_gui.exe" (
    echo [OK] GUI:  dist\vtg_image_util_gui.exe
    for %%A in ("dist\vtg_image_util_gui.exe") do echo       Size: %%~zA bytes
) else (
    echo [FAIL] GUI executable not created
)

REM Create distribution zip
echo.
echo Creating distribution package...
set ZIPNAME=vtg_image_util_v%VERSION%.zip

if exist "dist\%ZIPNAME%" del "dist\%ZIPNAME%"

REM Use PowerShell to create zip
powershell -Command "Compress-Archive -Path 'dist\vtg_image_util.exe', 'dist\vtg_image_util_gui.exe' -DestinationPath 'dist\%ZIPNAME%'" 2>nul

if exist "dist\%ZIPNAME%" (
    echo [OK] Package: dist\%ZIPNAME%
    for %%A in ("dist\%ZIPNAME%") do echo       Size: %%~zA bytes
) else (
    echo [WARN] Could not create zip package
)

echo.
echo Build complete!
echo.
