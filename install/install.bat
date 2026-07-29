@echo off

:: Script to install the blender nif scripts

set "DIR=%~dps0"
:: remove trailing backslash
if "%DIR:~-1%" == "\" set "DIR=%DIR:~0,-1%"
for %%I in ("%DIR%\..") do set "ROOT=%%~fI"
set "NAME=blender_niftools_addon"
set "MANIFEST=%ROOT%\io_scene_niftools\blender_manifest.toml"
for /f %%i in ('python -c "import sys, tomllib; print(tomllib.load(open(sys.argv[1], 'rb'))['version'])" "%MANIFEST%"') do set VERSION=%%i
for /f %%i in ('git rev-parse --short HEAD') do set HASH=%%i
:: Use PowerShell to get current date in YYYY-MM-DD format independent of local format
for /f %%i in ('powershell -executionpolicy bypass -Command Get-Date -Format "yyyy-MM-dd"') do set DATE=%%i
set "ZIP_NAME=%NAME%-%VERSION%-%DATE%-%HASH%"

if "%BLENDER_EXTENSIONS_DIR%" == "" if not exist "%BLENDER_EXTENSIONS_DIR%" (
echo. "Update BLENDER_EXTENSIONS_DIR to the folder where the blender extensions reside, such as:"
echo. "set BLENDER_EXTENSIONS_DIR=%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default"
echo.
pause
goto end
)

echo "Blender addons directory : %BLENDER_EXTENSIONS_DIR%"
echo. "Installing to: %BLENDER_EXTENSIONS_DIR%\io_scene_niftools"

:: create zip
echo. "Building artifact"
call "%DIR%\makezip.bat"

:: remove old files
echo.Removing old installation
if exist "%BLENDER_EXTENSIONS_DIR%\io_scene_niftools" rmdir /s /q "%BLENDER_EXTENSIONS_DIR%\io_scene_niftools"

:: copy files from repository to blender extensions folder
mkdir "%BLENDER_EXTENSIONS_DIR%\io_scene_niftools"
powershell -executionpolicy bypass -Command "%DIR%\unzip.ps1" -source '%DIR%\%ZIP_NAME%.zip' -destination '%BLENDER_EXTENSIONS_DIR%\io_scene_niftools'

:end