@echo off
REM Build Alexander engine on Windows using MSYS2 / MinGW-w64.
REM
REM Prerequisites:
REM   1. Install MSYS2 from https://www.msys2.org/
REM   2. In MSYS2 terminal: pacman -S mingw-w64-x86_64-gcc make
REM   3. Run this script from the repo root or tests\ folder.
REM
REM Usage:
REM   tests\build_engine.bat
REM   tests\build_engine.bat --clean

setlocal enabledelayedexpansion

REM ── Locate repo root (one level up from this script) ─────────────────────────
set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%.."
set "SRC=%REPO_ROOT%\Alexander\src"

if not exist "%SRC%\Makefile" (
    echo ERROR: Alexander\src\Makefile not found.  Expected: %SRC%
    exit /b 1
)

REM ── Locate MSYS2 ─────────────────────────────────────────────────────────────
set "MSYS2_ROOT=C:\tools\msys64"
if not exist "%MSYS2_ROOT%\usr\bin\make.exe" (
    set "MSYS2_ROOT=C:\msys64"
)
if not exist "%MSYS2_ROOT%\usr\bin\make.exe" (
    echo ERROR: MSYS2 not found.  Install from https://www.msys2.org/ and re-run.
    echo        Expected at C:\tools\msys64 or C:\msys64
    exit /b 1
)

set "PATH=%MSYS2_ROOT%\mingw64\bin;%MSYS2_ROOT%\usr\bin;%PATH%"

echo Platform : Windows x86-64
echo ARCH     : x86-64-avx2
echo COMP     : mingw
echo Jobs     : %NUMBER_OF_PROCESSORS%
echo.

pushd "%SRC%"

if "%1"=="--clean" (
    echo Cleaning previous build...
    mingw32-make clean
)

echo Building...
mingw32-make -j%NUMBER_OF_PROCESSORS% build ARCH=x86-64-avx2 COMP=mingw

if not exist "alexander.exe" (
    echo ERROR: build finished but alexander.exe not found.
    popd
    exit /b 1
)

echo.
echo Built: %SRC%\alexander.exe
echo.
echo To use with eval_game.py:
echo   set ALEXANDER_ENGINE_PATH=%SRC%\alexander.exe
echo   python tests\eval_game.py --rerun-engine

popd
endlocal
