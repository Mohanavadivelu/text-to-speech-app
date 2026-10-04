@echo off
setlocal EnableDelayedExpansion

:: ═══════════════════════════════════════════════════════════════════════════════
::  Kokoro TTS  —  Standalone EXE Builder
::  Output : release\bin\KokoroTTS\KokoroTTS.exe
:: ═══════════════════════════════════════════════════════════════════════════════

:: Lives in scripts\ ; the project root is one level up. Output goes to release\bin.
set SCRIPT_DIR=%~dp0
if "%SCRIPT_DIR:~-1%"=="\" set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%
set ROOT=%SCRIPT_DIR%\..
:: Normalise (removes ..)
for %%I in ("%ROOT%") do set ROOT=%%~fI

set VENV=%ROOT%\venv
set APP=%ROOT%\app.py
set BIN=%ROOT%\release\bin
set BUILD_TMP=%ROOT%\release\build_tmp
set NAME=KokoroTTS

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║          Kokoro TTS  —  Standalone EXE Builder           ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.
echo   Project root : %ROOT%
echo   Output       : %BIN%\%NAME%\%NAME%.exe
echo.

:: ── [0] Sanity checks ─────────────────────────────────────────────────────────
if not exist "%VENV%\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at:
    echo         %VENV%
    echo.
    echo  Create it first:
    echo    python -m venv venv
    echo    venv\Scripts\pip install -r requirements.txt
    echo    venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu121
    echo.
    pause & exit /b 1
)

if not exist "%APP%" (
    echo [ERROR] Entry point not found: %APP%
    pause & exit /b 1
)

:: ── [1] Install / upgrade dependencies ───────────────────────────────────────
echo [1/4] Checking and installing dependencies...
echo.

:: Core runtime deps
"%VENV%\Scripts\pip.exe" install --quiet -r "%ROOT%\requirements.txt"
if errorlevel 1 ( echo [ERROR] Failed to install core deps. & pause & exit /b 1 )

:: PyInstaller
"%VENV%\Scripts\pip.exe" install --quiet --upgrade pyinstaller
if errorlevel 1 ( echo [ERROR] Failed to install PyInstaller. & pause & exit /b 1 )

:: Verify torch is installed (CUDA build preferred)
"%VENV%\Scripts\python.exe" -c "import torch; print('  torch', torch.__version__, '| CUDA:', torch.cuda.is_available())"
if errorlevel 1 (
    echo.
    echo  [WARN] torch not found — installing CPU build.
    echo         For GPU support run:
    echo           venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu121
    echo.
    "%VENV%\Scripts\pip.exe" install --quiet torch
    if errorlevel 1 ( echo [ERROR] torch install failed. & pause & exit /b 1 )
)

echo.
echo   All dependencies OK.
echo.

:: ── [2] Clean previous build ──────────────────────────────────────────────────
echo [2/4] Cleaning previous build artefacts...
if exist "%BUILD_TMP%"       rmdir /s /q "%BUILD_TMP%"
if exist "%BIN%\%NAME%"      rmdir /s /q "%BIN%\%NAME%"
if exist "%ROOT%\%NAME%.spec" del /q "%ROOT%\%NAME%.spec"
echo   Done.
echo.

:: ── [3] Run PyInstaller ───────────────────────────────────────────────────────
echo [3/4] Running PyInstaller (this may take several minutes)...
echo.

"%VENV%\Scripts\pyinstaller.exe" ^
    --name "%NAME%" ^
    --noconsole ^
    --onedir ^
    --distpath "%BIN%" ^
    --workpath "%BUILD_TMP%" ^
    --specpath "%BUILD_TMP%" ^
    --collect-all kokoro ^
    --collect-all misaki ^
    --collect-all soundfile ^
    --collect-all sounddevice ^
    --collect-all customtkinter ^
    --collect-all tkinterdnd2 ^
    --collect-all docx ^
    --collect-all pypdf ^
    --collect-all espeakng_loader ^
    --collect-all transformers ^
    --collect-all tokenizers ^
    --collect-all huggingface_hub ^
    --collect-all torch ^
    --hidden-import=torch ^
    --hidden-import=torchaudio ^
    --hidden-import=numpy ^
    --hidden-import=sounddevice ^
    --hidden-import=soundfile ^
    --hidden-import=kokoro ^
    --hidden-import=misaki ^
    --hidden-import=misaki.en ^
    --hidden-import=spacy ^
    --hidden-import=tkinter ^
    --hidden-import=tkinter.ttk ^
    --hidden-import=customtkinter ^
    --hidden-import=loguru ^
    --add-data "%ROOT%\ui;ui" ^
    --add-data "%ROOT%\core;core" ^
    "%APP%"

if errorlevel 1 (
    echo.
    echo  ╔══════════════════════════════════════════════════════════╗
    echo  ║  BUILD FAILED — check the output above for details       ║
    echo  ╚══════════════════════════════════════════════════════════╝
    pause & exit /b 1
)

:: ── [4] Clean up temp build files ────────────────────────────────────────────
echo.
echo [4/4] Cleaning up temporary build files...
if exist "%BUILD_TMP%"        rmdir /s /q "%BUILD_TMP%"
echo   Done.
echo.

:: ── Result ────────────────────────────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║                   BUILD SUCCESSFUL  ✓                    ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.
echo   Executable : %BIN%\%NAME%\%NAME%.exe
echo.
echo   ┌─ Distribution notes ──────────────────────────────────┐
echo   │  • Share the ENTIRE  release\bin\KokoroTTS\  folder   │
echo   │  • The .exe alone will NOT run without the folder     │
echo   │  • No Python installation required on target PC       │
echo   │  • audio_output\, logs\ and user_data\ are created     │
echo   │    next to KokoroTTS.exe on first run                 │
echo   │  • First launch downloads Kokoro model (~330 MB)      │
echo   │    and caches it in %%USERPROFILE%%\.cache\huggingface  │
echo   │  • Estimated folder size: 2 – 3 GB (PyTorch + CUDA)  │
echo   └───────────────────────────────────────────────────────┘
echo.
pause
