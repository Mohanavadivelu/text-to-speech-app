@echo off
setlocal EnableDelayedExpansion

:: ===========================================================================
::  Kokoro TTS  -  Standalone application builder
::
::  Usage:   scripts\build.bat            build (GPU build of PyTorch if an
::                                         NVIDIA GPU is found, else CPU)
::           scripts\build.bat --cpu      force the smaller CPU-only build
::
::  Creates the venv and installs everything it needs, so a fresh clone
::  only needs Python 3.9 - 3.12 with the "py" launcher.
::
::  Output:  release\bin\KokoroTTS\KokoroTTS.exe
::  Set NO_PAUSE=1 to skip the final "press any key" (for CI / scripts).
:: ===========================================================================

:: Lives in scripts\ ; the project root is one level up.
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%I in ("%SCRIPT_DIR%\..") do set "ROOT=%%~fI"

set "VENV=%ROOT%\venv"
set "PY=%VENV%\Scripts\python.exe"
set "APP=%ROOT%\app.py"
set "REQ=%ROOT%\requirements.txt"
set "BIN=%ROOT%\release\bin"
set "BUILD_TMP=%ROOT%\release\build_tmp"
set "KEEP_TMP=%ROOT%\release\keep_tmp"
set "NAME=KokoroTTS"
set "PY_MIN=9"
set "PY_MAX=12"

set "FORCE_CPU=0"
if /i "%~1"=="--cpu" set "FORCE_CPU=1"

echo.
echo  ==========================================================
echo     Kokoro TTS  -  Standalone application builder
echo  ==========================================================
echo.
echo   Project root : %ROOT%
echo   Output       : %BIN%\%NAME%\%NAME%.exe
echo.

if not exist "%APP%" (
    echo [ERROR] Entry point not found: %APP%
    goto :fail
)

:: --- [1/6] Python virtual environment --------------------------------------
echo [1/6] Checking the Python environment...
set "NEED_VENV=1"
if exist "%PY%" (
    "%PY%" -c "import sys; sys.exit(0 if %PY_MIN% <= sys.version_info.minor <= %PY_MAX% and sys.version_info.major == 3 else 1)" >nul 2>&1
    if not errorlevel 1 set "NEED_VENV=0"
)
if "%NEED_VENV%"=="1" (
    if exist "%VENV%" (
        echo   Existing venv uses an unsupported Python - recreating it.
        rmdir /s /q "%VENV%"
    )
    set "BASE_PY="
    for %%v in (3.12 3.11 3.10 3.9) do (
        if not defined BASE_PY (
            py -%%v --version >nul 2>&1
            if not errorlevel 1 set "BASE_PY=py -%%v"
        )
    )
    if not defined BASE_PY (
        echo [ERROR] No Python 3.9 - 3.12 found. PyTorch does not support 3.13 yet.
        echo         Install Python 3.12 from https://python.org with the "py" launcher.
        goto :fail
    )
    echo   Creating venv with !BASE_PY!...
    !BASE_PY! -m venv "%VENV%"
    if errorlevel 1 ( echo [ERROR] Could not create the virtual environment. & goto :fail )
)
for /f "tokens=*" %%v in ('"%PY%" --version 2^>^&1') do echo   %%v  ^(%VENV%^)
"%PY%" -m pip install --quiet --upgrade pip >nul 2>&1
echo.

:: --- [2/6] PyTorch ------------------------------------------------------------
echo [2/6] Checking PyTorch...
"%PY%" -c "import torch" >nul 2>&1
if errorlevel 1 (
    set "TORCH_INDEX=https://download.pytorch.org/whl/cpu"
    set "TORCH_KIND=CPU"
    if "%FORCE_CPU%"=="0" (
        nvidia-smi >nul 2>&1
        if not errorlevel 1 (
            set "TORCH_INDEX=https://download.pytorch.org/whl/cu121"
            set "TORCH_KIND=CUDA"
        )
    )
    echo   Installing the !TORCH_KIND! build of PyTorch ^(large download^)...
    "%PY%" -m pip install torch torchaudio --index-url !TORCH_INDEX!
    if errorlevel 1 ( echo [ERROR] PyTorch installation failed. & goto :fail )
) else (
    if "%FORCE_CPU%"=="1" (
        "%PY%" -c "import torch, sys; sys.exit(1 if torch.version.cuda else 0)" >nul 2>&1
        if errorlevel 1 (
            echo   --cpu given: replacing the CUDA build with the CPU build...
            "%PY%" -m pip uninstall -y torch torchaudio >nul
            "%PY%" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
            if errorlevel 1 ( echo [ERROR] PyTorch installation failed. & goto :fail )
        )
    )
)
"%PY%" -c "import torch; print('  torch', torch.__version__, '| CUDA build:', bool(torch.version.cuda), '| GPU available:', torch.cuda.is_available())"
echo.

:: --- [3/6] App dependencies and PyInstaller ------------------------------
echo [3/6] Installing app dependencies and PyInstaller...
"%PY%" -m pip install --quiet -r "%REQ%" pyinstaller
if errorlevel 1 ( echo [ERROR] Dependency installation failed. & goto :fail )
:: English text processing needs this spaCy model inside the bundle
"%PY%" -c "import en_core_web_sm" >nul 2>&1
if errorlevel 1 (
    echo   Downloading the spaCy English model...
    "%PY%" -m spacy download en_core_web_sm
    if errorlevel 1 ( echo [ERROR] Could not install en_core_web_sm. & goto :fail )
)
echo   Done.
echo.

:: --- [4/6] Clean previous build ------------------------------------------
:: The app keeps audio_output\, logs\ and user_data\ next to the exe; move them
:: aside so a rebuild never deletes the user's audio or settings.
echo [4/6] Cleaning previous build...
if exist "%BUILD_TMP%" rmdir /s /q "%BUILD_TMP%"
if exist "%KEEP_TMP%" call :restore_user_folders
for %%d in (audio_output logs user_data) do (
    if exist "%BIN%\%NAME%\%%d" (
        if not exist "%KEEP_TMP%" mkdir "%KEEP_TMP%"
        move "%BIN%\%NAME%\%%d" "%KEEP_TMP%\%%d" >nul
        if errorlevel 1 ( echo [ERROR] Could not preserve %%d. Is KokoroTTS.exe still running? & goto :fail )
        echo   Preserved %%d\
    )
)
if exist "%BIN%\%NAME%" rmdir /s /q "%BIN%\%NAME%"
if exist "%BIN%\%NAME%" ( echo [ERROR] Could not delete the old build. Is KokoroTTS.exe still running? & goto :fail )
echo   Done.
echo.

:: --- [5/6] PyInstaller --------------------------------------------------------
echo [5/6] Running PyInstaller (this takes several minutes)...
echo.
"%PY%" -m PyInstaller ^
    --noconfirm ^
    --name "%NAME%" ^
    --noconsole ^
    --onedir ^
    --distpath "%BIN%" ^
    --workpath "%BUILD_TMP%" ^
    --specpath "%BUILD_TMP%" ^
    --paths "%ROOT%" ^
    --collect-all kokoro ^
    --collect-all misaki ^
    --collect-all espeakng_loader ^
    --collect-all phonemizer ^
    --collect-all spacy ^
    --collect-all en_core_web_sm ^
    --collect-all soundfile ^
    --collect-all sounddevice ^
    --collect-all customtkinter ^
    --collect-all tkinterdnd2 ^
    --collect-all segments ^
    --collect-all csvw ^
    --collect-data language_tags ^
    --collect-data babel ^
    --collect-data jsonschema_specifications ^
    --collect-data thinc ^
    --collect-all docx ^
    --collect-all pypdf ^
    --collect-all transformers ^
    --collect-all tokenizers ^
    --collect-all huggingface_hub ^
    --collect-all torch ^
    --hidden-import=loguru ^
    --hidden-import=misaki.en ^
    --hidden-import=misaki.espeak ^
    --hidden-import=tkinter.ttk ^
    --exclude-module=matplotlib ^
    --exclude-module=IPython ^
    --exclude-module=pytest ^
    "%APP%"
set "PYI_ERR=%errorlevel%"
call :restore_user_folders
if not "%PYI_ERR%"=="0" (
    echo.
    echo [ERROR] PyInstaller failed - see the output above.
    goto :fail
)

:: --- [6/6] Verify --------------------------------------------------------------
echo.
echo [6/6] Verifying the build...
if not exist "%BIN%\%NAME%\%NAME%.exe" ( echo [ERROR] %NAME%.exe was not created. & goto :fail )
if exist "%BUILD_TMP%" rmdir /s /q "%BUILD_TMP%"
for /f %%s in ('powershell -NoProfile -Command "[math]::Round((Get-ChildItem -LiteralPath '%BIN%\%NAME%' -Recurse -File | Measure-Object Length -Sum).Sum / 1GB, 2)"') do set "SIZE_GB=%%s"

echo.
echo  ==========================================================
echo     BUILD SUCCESSFUL
echo  ==========================================================
echo.
echo   Executable : %BIN%\%NAME%\%NAME%.exe
echo   Folder size: !SIZE_GB! GB
echo.
echo   Distribution notes:
echo    - Share the whole release\bin\%NAME%\ folder; the exe needs it.
echo    - No Python installation is needed on the target PC.
echo    - audio_output\, logs\ and user_data\ are created next to the exe.
echo    - The first generation downloads the voice model (about 330 MB)
echo      into %%USERPROFILE%%\.cache\huggingface.
echo    - Problems? Check logs\kokoro_tts.log next to the exe.
echo.
if not defined NO_PAUSE pause
exit /b 0

:restore_user_folders
if not exist "%KEEP_TMP%" exit /b 0
if not exist "%BIN%\%NAME%" mkdir "%BIN%\%NAME%"
for %%d in (audio_output logs user_data) do (
    if exist "%KEEP_TMP%\%%d" if not exist "%BIN%\%NAME%\%%d" move "%KEEP_TMP%\%%d" "%BIN%\%NAME%\%%d" >nul
)
rmdir "%KEEP_TMP%" 2>nul
echo   Restored audio_output\, logs\ and user_data\ next to the exe.
exit /b 0

:fail
call :restore_user_folders
echo.
echo  BUILD FAILED
echo.
if not defined NO_PAUSE pause
exit /b 1
