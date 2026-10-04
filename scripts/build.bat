@echo off
setlocal EnableDelayedExpansion

:: ===========================================================================
::  Kokoro TTS  -  Standalone application builder
::
::  Usage:   scripts\build.bat                    build the app
::           scripts\build.bat --refresh-gpu-list re-resolve the GPU pack list
::
::  Builds the small base app with the CPU engine (ONNX Runtime, no PyTorch).
::  The voice model (~330 MB) and the optional GPU pack (PyTorch + CUDA) are
::  downloaded by the app itself, so neither is bundled.
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

set "REFRESH_GPU=0"
if /i "%~1"=="--refresh-gpu-list" set "REFRESH_GPU=1"
set "MANIFEST=%ROOT%\core\gpu_manifest.json"

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

:: --- [2/6] App dependencies and PyInstaller ------------------------------
echo [2/6] Installing app dependencies and PyInstaller...
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

:: --- [3/6] GPU pack list ------------------------------------------------------
:: core\gpu_manifest.json pins every wheel of the optional GPU pack for this
:: Python version. Regenerate it when missing, for another Python, or on request.
echo [3/6] Checking the GPU pack list...
if exist "%VENV%\Lib\site-packages\torch" (
    echo [ERROR] PyTorch is installed in venv\. The base app must be built without it.
    echo         Delete the venv folder and run this script again.
    goto :fail
)
set "NEED_LIST=%REFRESH_GPU%"
if not exist "%MANIFEST%" set "NEED_LIST=1"
if "%NEED_LIST%"=="0" (
    "%PY%" -c "import json,sys; m=json.load(open(r'%MANIFEST%')); sys.exit(0 if m['python']=='cp%%d%%d' %% sys.version_info[:2] else 1)" >nul 2>&1
    if errorlevel 1 set "NEED_LIST=1"
)
if "%NEED_LIST%"=="1" (
    echo   Resolving PyTorch + CUDA wheels for this Python...
    "%PY%" "%ROOT%\scripts\make_gpu_manifest.py"
    if errorlevel 1 ( echo [ERROR] Could not create the GPU pack list. & goto :fail )
) else (
    echo   Up to date.
)
echo.

:: --- [4/6] Clean previous build ------------------------------------------
:: The app keeps audio_output\, logs\, user_data\, models\ and engines\ next to
:: the exe; move them aside so a rebuild never deletes audio, settings or downloads.
echo [4/6] Cleaning previous build...
if exist "%BUILD_TMP%" rmdir /s /q "%BUILD_TMP%"
if exist "%KEEP_TMP%" call :restore_user_folders
for %%d in (audio_output logs user_data models engines) do (
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
:: Packages the base app shares with the GPU pack must be bundled whole: the
:: bundled copy wins over the pack's, and torch/kokoro use parts the base app
:: does not (found by running the GPU engine: tqdm, jinja2, loguru, numpy...).
:: transformers also checks their versions through package metadata.
:: Rust/abi3 extensions in the GPU pack (safetensors, tokenizers) link against
:: python3.dll, which PyInstaller does not bundle by itself.
"%PY%" -c "import sys, os; print(os.path.join(sys.base_prefix, 'python3.dll'))" > "%ROOT%\release\py3dll.txt"
set /p PY3DLL=<"%ROOT%\release\py3dll.txt"
del "%ROOT%\release\py3dll.txt" >nul 2>&1
if not exist "%PY3DLL%" ( echo [ERROR] python3.dll not found next to the base Python. & goto :fail )
"%PY%" -m PyInstaller ^
    --noconfirm ^
    --name "%NAME%" ^
    --noconsole ^
    --onedir ^
    --distpath "%BIN%" ^
    --workpath "%BUILD_TMP%" ^
    --specpath "%BUILD_TMP%" ^
    --paths "%ROOT%" ^
    --additional-hooks-dir "%ROOT%\scripts\pyinstaller_hooks" ^
    --add-data "%MANIFEST%;core" ^
    --collect-all onnxruntime ^
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
    --add-binary "%PY3DLL%;." ^
    --copy-metadata tqdm ^
    --copy-metadata numpy ^
    --copy-metadata regex ^
    --copy-metadata packaging ^
    --copy-metadata requests ^
    --copy-metadata jinja2 ^
    --copy-metadata markupsafe ^
    --copy-metadata typing_extensions ^
    --copy-metadata urllib3 ^
    --copy-metadata idna ^
    --copy-metadata certifi ^
    --copy-metadata charset_normalizer ^
    --copy-metadata loguru ^
    --collect-submodules tqdm ^
    --collect-submodules jinja2 ^
    --collect-submodules markupsafe ^
    --collect-submodules numpy ^
    --collect-submodules loguru ^
    --collect-submodules win32_setctime ^
    --collect-submodules requests ^
    --collect-submodules packaging ^
    --collect-submodules typing_extensions ^
    --collect-submodules urllib3 ^
    --collect-submodules regex ^
    --hidden-import=loguru ^
    --hidden-import=misaki.en ^
    --hidden-import=misaki.espeak ^
    --hidden-import=tkinter.ttk ^
    --exclude-module=torch ^
    --exclude-module=torchaudio ^
    --exclude-module=kokoro ^
    --exclude-module=transformers ^
    --exclude-module=onnx ^
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
:: App size only (exe + _internal), not the user's downloads kept next to it
for /f %%s in ('powershell -NoProfile -Command "[math]::Round(((Get-ChildItem -LiteralPath '%BIN%\%NAME%\_internal' -Recurse -File | Measure-Object Length -Sum).Sum + (Get-Item -LiteralPath '%BIN%\%NAME%\%NAME%.exe').Length) / 1MB)"') do set "SIZE_MB=%%s"

echo.
echo  ==========================================================
echo     BUILD SUCCESSFUL
echo  ==========================================================
echo.
echo   Executable : %BIN%\%NAME%\%NAME%.exe
echo   App size   : !SIZE_MB! MB  (downloads kept next to it are not counted)
echo.
echo   Distribution notes:
echo    - Share the whole release\bin\%NAME%\ folder; the exe needs it.
echo    - No Python installation is needed on the target PC.
echo    - audio_output\, logs\ and user_data\ are created next to the exe.
echo    - First launch downloads the voice model (about 345 MB) into models\.
echo    - NVIDIA users can add the GPU pack from Voice settings - Engine.
echo    - Problems? Check logs\kokoro_tts.log next to the exe.
echo.
if not defined NO_PAUSE pause
exit /b 0

:restore_user_folders
if not exist "%KEEP_TMP%" exit /b 0
if not exist "%BIN%\%NAME%" mkdir "%BIN%\%NAME%"
for %%d in (audio_output logs user_data models engines) do (
    if exist "%KEEP_TMP%\%%d" if not exist "%BIN%\%NAME%\%%d" move "%KEEP_TMP%\%%d" "%BIN%\%NAME%\%%d" >nul
)
rmdir "%KEEP_TMP%" 2>nul
echo   Restored the app data folders next to the exe.
exit /b 0

:fail
call :restore_user_folders
echo.
echo  BUILD FAILED
echo.
if not defined NO_PAUSE pause
exit /b 1
