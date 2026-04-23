@echo off
setlocal EnableDelayedExpansion

set WORKSPACE=%~dp0
if "%WORKSPACE:~-1%"=="\" set WORKSPACE=%WORKSPACE:~0,-1%

set VENV=%WORKSPACE%\venv
set APP=%WORKSPACE%\app.py
set REQUIREMENTS=%WORKSPACE%\requirements.txt

:: kokoro + torch + misaki require Python 3.9 – 3.12
:: Python 3.13+ is not yet supported by PyTorch
set PY_MIN=9
set PY_MAX=12

echo =============================================================
echo  Kokoro TTS  --  Launcher
echo =============================================================
echo.
echo  Workspace : %WORKSPACE%
echo  App       : %APP%
echo.

:: ── 1. Check if venv exists and has a compatible Python ──────────────────────
set NEED_CREATE=0

if not exist "%VENV%\Scripts\python.exe" (
    echo  [INFO] No virtual environment found -- will create one.
    set NEED_CREATE=1
) else (
    for /f "tokens=*" %%v in ('"%VENV%\Scripts\python.exe" --version 2^>^&1') do set VENV_PY_STR=%%v

    :: Let Python itself do the version range check to avoid batch string-vs-numeric comparison bugs
    "%VENV%\Scripts\python.exe" -c "import sys; exit(0 if %PY_MIN% <= sys.version_info.minor <= %PY_MAX% else 1)" >nul 2>&1
    if errorlevel 1 (
        echo  [WARN] Venv uses !VENV_PY_STR! -- incompatible with kokoro/torch ^(need 3.%PY_MIN% - 3.%PY_MAX%^).
        set NEED_CREATE=1
    ) else (
        echo  Venv   : %VENV%
        echo  Python : !VENV_PY_STR!
        echo.
    )
)

:: ── 2. If needed, delete old venv, find a compatible Python, recreate ─────────
if "%NEED_CREATE%"=="1" (
    if exist "%VENV%" (
        echo  [INFO] Removing incompatible venv...
        rmdir /s /q "%VENV%"
        echo  [OK]   Removed.
    )

    echo.
    echo  [INFO] Searching for compatible Python ^(3.%PY_MIN% - 3.%PY_MAX%^)...
    echo.

    set PYTHON_EXE=
    set PYTHON_VER=
    for %%v in (3.12 3.11 3.10 3.9) do (
        if not defined PYTHON_EXE (
            py -%%v --version >nul 2>&1
            if not errorlevel 1 (
                set PYTHON_EXE=py -%%v
                set PYTHON_VER=%%v
                echo  [FOUND] Python %%v via py launcher.
            )
        )
    )

    if not defined PYTHON_EXE (
        echo.
        echo  [ERROR] No compatible Python ^(3.9 - 3.12^) found on this system.
        echo.
        echo          Install Python 3.12 from https://python.org
        echo          Make sure to check "Add to PATH" and include py launcher.
        echo.
        pause & exit /b 1
    )

    echo.
    echo  [INFO] Creating virtual environment with Python !PYTHON_VER!...
    !PYTHON_EXE! -m venv "%VENV%"
    if errorlevel 1 (
        echo  [ERROR] Failed to create virtual environment.
        pause & exit /b 1
    )

    for /f "tokens=*" %%v in ('"%VENV%\Scripts\python.exe" --version 2^>^&1') do set VENV_PY_STR=%%v
    echo  [OK]   Virtual environment created.
    echo.
    echo  Venv   : %VENV%
    echo  Python : !VENV_PY_STR!
    echo.
)

:: ── 3. Check dependencies ────────────────────────────────────────────────────
if not exist "%VENV%\Scripts\pip.exe" (
    echo  [ERROR] pip not found in venv. Delete the venv folder and re-run.
    pause & exit /b 1
)

echo  Checking dependencies...
echo.
set MISSING=0
for /f "eol=# tokens=1 delims=>[=[ " %%p in (%REQUIREMENTS%) do (
    "%VENV%\Scripts\pip.exe" show %%p >nul 2>&1
    if errorlevel 1 (
        echo   [MISSING] %%p
        set MISSING=1
    ) else (
        echo   [OK]      %%p
    )
)
echo.

if "%MISSING%"=="1" (
    :: Install PyTorch CPU-only first so kokoro does not pull in the CUDA build.
    :: The CUDA build requires CUDA DLLs that cause c10.dll to fail on machines
    :: without a GPU / CUDA toolkit installed.
    "%VENV%\Scripts\pip.exe" show torch >nul 2>&1
    if errorlevel 1 (
        echo  [INFO] Installing PyTorch CPU build...
        echo.
        "%VENV%\Scripts\pip.exe" install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
        if errorlevel 1 (
            echo.
            echo  [ERROR] Failed to install PyTorch. Check your internet connection.
            pause & exit /b 1
        )
        echo.
        echo  [OK]   PyTorch CPU installed.
        echo.
    )

    echo  [INFO] Installing remaining packages from requirements.txt...
    echo.
    "%VENV%\Scripts\pip.exe" install -r "%REQUIREMENTS%" --extra-index-url https://download.pytorch.org/whl/cpu
    if errorlevel 1 (
        echo.
        echo  [ERROR] Installation failed. Check the output above for details.
        pause & exit /b 1
    )
    echo.
    echo  [OK]   All packages installed successfully.
    echo.
)

:: ── 3b. Verify torch is CPU build (not CUDA) ────────────────────────────────
"%VENV%\Scripts\pip.exe" show torch >nul 2>&1
if not errorlevel 1 (
    "%VENV%\Scripts\python.exe" -c "import torch; exit(1 if torch.version.cuda else 0)" >nul 2>&1
    if errorlevel 1 (
        echo  [WARN] CUDA build of PyTorch detected -- reinstalling CPU build...
        echo.
        "%VENV%\Scripts\pip.exe" install torch torchaudio --index-url https://download.pytorch.org/whl/cpu --force-reinstall
        if errorlevel 1 (
            echo  [ERROR] Failed to reinstall PyTorch CPU build.
            pause & exit /b 1
        )
        echo.
        echo  [OK]   PyTorch CPU build installed.
        echo.
    ) else (
        echo  [OK]   PyTorch CPU build confirmed.
        echo.
    )
)

:: ── 4. Activate venv ─────────────────────────────────────────────────────────
call "%VENV%\Scripts\activate.bat"
echo  [OK]   Venv activated: %VIRTUAL_ENV%
echo.

:: ── 5. Launch ────────────────────────────────────────────────────────────────
echo =============================================================
echo  Starting Kokoro TTS...
echo =============================================================
echo.
python "%APP%"
pause
