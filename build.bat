@echo off
setlocal EnableDelayedExpansion

:: ── Use script directory as workspace root (portable) ─────────────────────────
set WORKSPACE=%~dp0
:: Remove trailing backslash
if "%WORKSPACE:~-1%"=="\" set WORKSPACE=%WORKSPACE:~0,-1%

set VENV=%WORKSPACE%\venv
set APP=%WORKSPACE%\app.py
set DIST=%WORKSPACE%\dist
set BUILD=%WORKSPACE%\build_tmp
set NAME=KokoroTTS

echo =============================================================
echo  Kokoro TTS  --  Standalone EXE Builder
echo =============================================================
echo.
echo  Workspace : %WORKSPACE%
echo  Output    : %DIST%\%NAME%\%NAME%.exe
echo.

:: ── Check venv exists ────────────────────────────────────────────────────────
if not exist "%VENV%\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at:
    echo         %VENV%
    echo.
    echo         Run setup first:
    echo           python -m venv venv
    echo           venv\Scripts\pip install -r requirements.txt
    echo.
    pause & exit /b 1
)

:: ── Install / upgrade PyInstaller ────────────────────────────────────────────
echo [1/3] Installing / upgrading PyInstaller...
"%VENV%\Scripts\pip.exe" install --quiet --upgrade pyinstaller
if errorlevel 1 (
    echo [ERROR] pip failed. Check your internet connection or venv.
    pause & exit /b 1
)
echo       Done.
echo.

:: ── Clean previous build ─────────────────────────────────────────────────────
echo [2/3] Cleaning previous build artefacts...
if exist "%BUILD%"        rmdir /s /q "%BUILD%"
if exist "%DIST%\%NAME%"  rmdir /s /q "%DIST%\%NAME%"
if exist "%WORKSPACE%\%NAME%.spec" del /q "%WORKSPACE%\%NAME%.spec"
echo       Done.
echo.

:: ── PyInstaller ──────────────────────────────────────────────────────────────
echo [3/3] Running PyInstaller (this may take a few minutes)...
echo.

"%VENV%\Scripts\pyinstaller.exe" ^
    --name "%NAME%" ^
    --noconsole ^
    --onedir ^
    --distpath "%DIST%" ^
    --workpath "%BUILD%" ^
    --collect-all kokoro ^
    --collect-all misaki ^
    --collect-all soundfile ^
    --collect-all sounddevice ^
    --collect-all espeakng_loader ^
    --collect-all transformers ^
    --collect-all tokenizers ^
    --collect-all huggingface_hub ^
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
    "%APP%"

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller failed. Check the output above for details.
    pause & exit /b 1
)

:: ── Result ───────────────────────────────────────────────────────────────────
echo.
echo =============================================================
echo  BUILD SUCCESSFUL
echo =============================================================
echo.
echo  Executable : %DIST%\%NAME%\%NAME%.exe
echo.
echo  NOTE: The dist\KokoroTTS\ folder is the complete app.
echo        Copy the ENTIRE folder — the .exe alone will not run.
echo.
echo  NOTE: On first launch the app will download the Kokoro model
echo        (~330 MB) once and cache it in:
echo        %%USERPROFILE%%\.cache\huggingface\hub
echo        All subsequent launches are fully offline.
echo.
echo  Estimated dist folder size: ~1.5 - 2.5 GB (due to PyTorch)
echo.
pause
