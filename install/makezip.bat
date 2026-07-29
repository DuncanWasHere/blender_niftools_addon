@echo off

set "DIR=%~dps0"
:: remove trailing backslash
if "%DIR:~-1%" == "\" (
    set "DIR=%DIR:~0,-1%"
)

for %%I in ("%DIR%\..") do set "ROOT=%%~fI"
set "NAME=blender_niftools_addon"
set "MANIFEST=%ROOT%\io_scene_niftools\blender_manifest.toml"
for /f %%i in ('python -c "import sys, tomllib; print(tomllib.load(open(sys.argv[1], 'rb'))['version'])" "%MANIFEST%"') do set VERSION=%%i
:: Abuse for loop to execute and store command output
for /f %%i in ('git rev-parse --short HEAD') do set HASH=%%i
:: Use PowerShell so the date format does not depend on the system locale
for /f %%i in ('powershell -executionpolicy bypass -Command Get-Date -Format "yyyy-MM-dd"') do set DATE=%%i
set "ZIP_NAME=%NAME%-v%VERSION%-%DATE%-%HASH%"
set "PYFFI_VERSION=2.2.4.dev3"
set "DEPS=io_scene_niftools\dependencies"
set "WHEELS=io_scene_niftools\wheels"
if exist "%DIR%\temp" rmdir /s /q "%DIR%\temp"

mkdir "%DIR%"\temp

pushd "%DIR%"\temp
mkdir io_scene_niftools
xcopy /s "%ROOT%\io_scene_niftools" io_scene_niftools
mkdir "%DEPS%"
mkdir "%WHEELS%"

python -m pip download "PyFFI==%PYFFI_VERSION%" --no-deps --only-binary=:all: --dest "%WHEELS%" || exit 1
docker compose -f "%DIR%\docker-compose.yml" up --build --abort-on-container-exit --exit-code-from codegen || exit 1

:: docker-compose mounts %DEPS% as /output
if "%GENERATED_FOLDER%" == "" set "GENERATED_FOLDER=%DEPS%\generated"
xcopy "%GENERATED_FOLDER%" "%DEPS%\nifgen" /s /q /i || exit 1
:: drop the staging copy so the zip does not carry the tree twice
if exist "%DEPS%\generated" rmdir /s /q "%DEPS%\generated"
:: rename generated folder to nifgen
python "%DIR%\rename_nifgen.py" "%DEPS%\nifgen" || exit 1

:: nifgen ships as a wheel to pass Blender policy check
python "%DIR%\build_nifgen_wheel.py" "%DEPS%\nifgen" "%VERSION%" "%WHEELS%" || exit 1
rmdir /s /q "%DEPS%"

xcopy "%ROOT%"\AUTHORS.rst io_scene_niftools
xcopy "%ROOT%"\CHANGELOG.rst io_scene_niftools
xcopy "%ROOT%"\LICENSE.rst io_scene_niftools
xcopy "%ROOT%"\README.rst io_scene_niftools

:: remove all __pycache__ folders
for /d /r %%x in (*) do if "%%~nx" == "__pycache__" rd %%x /s /q

popd

set "COMMAND_FILE=%DIR%\zip.ps1"
set "COMMAND_FILE=%COMMAND_FILE: =` %"

:: Extension zip needs blender_manifest.toml in the root
set "SOURCE_DIR=%DIR%\temp\io_scene_niftools"
set "SOURCE_DIR=%SOURCE_DIR: =` %"

set "DESTINATION_DIR=%DIR%\%ZIP_NAME%.zip"
set "DESTINATION_DIR=%DESTINATION_DIR: =` %"

powershell -executionpolicy bypass -Command "%COMMAND_FILE%" -source "%SOURCE_DIR%" -destination "%DESTINATION_DIR%" || exit 1
rmdir /s /q "%DIR%\temp"
