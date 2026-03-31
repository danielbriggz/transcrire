@echo off
:: ============================================================
:: Transcrire — Installer & Launcher
:: Developer: Daniel "Briggz" Adisa
:: ============================================================
:: Double-click this file to install or launch Transcrire.
::
:: First run  — downloads and installs everything automatically
:: Every run  — launches Transcrire directly
::
:: What this does:
::   1. Checks Python is installed
::   2. Bootstraps uv silently (no manual install required)
::   3. Downloads the project from GitHub on first run
::   4. Creates a virtual environment via uv
::   5. Installs all dependencies from the lockfile
::   6. Collects API keys and saves them to .env
::   7. Launches Transcrire
:: ============================================================

title Transcrire

:: ============================================================
:: PATHS
:: APP_DIR  — scripts, venv, database, config (hidden)
:: USER_DIR — input/ and output/ folders (Desktop, user-facing)
:: UV_DIR   — standalone uv binary location
:: ============================================================
set APP_DIR=%APPDATA%\Transcrire
set USER_DIR=%USERPROFILE%\Desktop\Transcrire
set UV_DIR=%APP_DIR%\bin
set UV_EXE=%UV_DIR%\uv.exe
set VENV=%APP_DIR%\.venv
set PYTHON=%VENV%\Scripts\python.exe
set REPO_ZIP=https://github.com/danielbriggz/transcrire/archive/refs/heads/rebuild.zip

echo.
echo  ============================================
echo         ^|^|^| TRANSCRIRE ^|^|^|
echo  ============================================
echo.

:: ============================================================
:: STEP 1: CHECK PYTHON
:: ============================================================
echo  Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Python is not installed or not on PATH.
    echo.
    echo  Please install Python 3.10-3.12 from:
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During install, check "Add Python to PATH"
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  Python %PYVER% found.

for /f "tokens=2 delims=." %%m in ('python --version 2^>^&1') do set PYMINOR=%%m
if %PYMINOR% GEQ 13 (
    echo.
    echo  [WARNING] Python 3.13+ detected.
    echo  Recommended: Python 3.10-3.12
    echo  Some audio features may not work correctly.
    echo.
    timeout /t 5 >nul
)

:: ============================================================
:: STEP 2: BOOTSTRAP uv SILENTLY
:: Downloads the standalone uv binary if not already present.
:: No pip install uv — this is self-contained.
:: ============================================================
if exist "%UV_EXE%" goto UV_READY

echo  Bootstrapping uv package manager...
if not exist "%UV_DIR%" mkdir "%UV_DIR%"

powershell -ExecutionPolicy ByPass -Command ^
  "$env:UV_INSTALL_DIR = '%UV_DIR%'; irm https://astral.sh/uv/install.ps1 | iex" >nul 2>&1

if not exist "%UV_EXE%" (
    :: Fallback: try pip install uv into system Python
    echo  Trying fallback install via pip...
    pip install uv >nul 2>&1
    for /f "delims=" %%i in ('python -c "import uv, os; print(os.path.dirname(uv.__file__))" 2^>nul') do set UV_EXE=%%i\uv.exe
)

if not exist "%UV_EXE%" (
    echo.
    echo  [ERROR] Could not bootstrap uv.
    echo  Please install manually: https://docs.astral.sh/uv/
    pause
    exit /b 1
)

:UV_READY
echo  uv ready.

:: ============================================================
:: STEP 3: CREATE USER FOLDERS ON DESKTOP
:: ============================================================
if not exist "%USER_DIR%\input"  mkdir "%USER_DIR%\input"
if not exist "%USER_DIR%\output" mkdir "%USER_DIR%\output"

:: ============================================================
:: STEP 4: CHECK IF ALREADY INSTALLED
:: If venv exists, skip installation and launch directly
:: ============================================================
if exist "%PYTHON%" (
    echo  Transcrire already installed.
    goto SYNC_AND_LAUNCH
)

:: ============================================================
:: STEP 5: FIRST-TIME INSTALLATION
:: ============================================================
echo.
echo  First-time setup. This will take a few minutes.
echo  Please do not close this window.
echo.

if not exist "%APP_DIR%" mkdir "%APP_DIR%"

:: ---- Download project from GitHub ----
echo  Downloading Transcrire...
curl -L -o "%APP_DIR%\transcrire.zip" "%REPO_ZIP%"
if errorlevel 1 (
    echo.
    echo  [ERROR] Download failed. Check your internet connection.
    pause
    exit /b 1
)

:: ---- Extract zip ----
echo  Extracting files...
powershell -Command "Expand-Archive -Path '%APP_DIR%\transcrire.zip' -DestinationPath '%APP_DIR%\extracted' -Force"
if errorlevel 1 (
    echo.
    echo  [ERROR] Extraction failed.
    pause
    exit /b 1
)

:: ---- Move files to APP_DIR ----
for /d %%i in ("%APP_DIR%\extracted\*") do (
    xcopy "%%i\*" "%APP_DIR%\" /E /I /Y >nul
)

:: ---- Clean up zip and temp folder ----
del "%APP_DIR%\transcrire.zip" >nul 2>&1
rmdir /s /q "%APP_DIR%\extracted" >nul 2>&1

:: ---- Create virtual environment via uv ----
echo  Creating Python environment...
"%UV_EXE%" venv "%VENV%" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Could not create virtual environment.
    pause
    exit /b 1
)

:: ---- Install dependencies from lockfile ----
echo  Installing dependencies...
cd /d "%APP_DIR%"
"%UV_EXE%" sync --frozen >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

:: ---- Collect API keys ----
if not exist "%APP_DIR%\.env" (
    echo.
    echo  ============================================
    echo   API Key Setup
    echo  ============================================
    echo.
    echo  Transcrire needs two free API keys to work.
    echo.
    echo  Get your Gemini key at:
    echo  https://aistudio.google.com/apikey
    echo.
    set /p GEMINI_KEY="  Paste your Gemini API key: "
    echo.
    echo  Get your Groq key at:
    echo  https://console.groq.com
    echo.
    set /p GROQ_KEY="  Paste your Groq API key: "
    echo.

    echo TRANSCRIRE_GEMINI_API_KEY=%GEMINI_KEY%> "%APP_DIR%\.env"
    echo TRANSCRIRE_GROQ_API_KEY=%GROQ_KEY%>> "%APP_DIR%\.env"

    echo  API keys saved.
    echo.
)

echo.
echo  ============================================
echo   Installation complete!
echo  ============================================
echo.
echo  Your files will be saved to:
echo  %USER_DIR%
echo.

:: ============================================================
:: STEP 6: SYNC AND LAUNCH
:: uv sync is a fast no-op if nothing has changed.
:: On updates it installs new dependencies automatically.
:: ============================================================
:SYNC_AND_LAUNCH
cd /d "%APP_DIR%"

:: ---- Set environment variables ----
set TRANSCRIRE_APPDATA=%APP_DIR%
set TRANSCRIRE_INPUT_FOLDER=%USER_DIR%\input
set TRANSCRIRE_OUTPUT_FOLDER=%USER_DIR%\output

:: ---- Check for missing API keys ----
if not exist "%APP_DIR%\.env" goto PROMPT_KEYS

findstr /i "TRANSCRIRE_GEMINI_API_KEY=." "%APP_DIR%\.env" >nul 2>&1
if errorlevel 1 goto PROMPT_KEYS

findstr /i "TRANSCRIRE_GROQ_API_KEY=." "%APP_DIR%\.env" >nul 2>&1
if errorlevel 1 goto PROMPT_KEYS

goto RUN

:PROMPT_KEYS
echo.
echo  ============================================
echo   Missing API Keys
echo  ============================================
echo.

set EXISTING_GEMINI=
set EXISTING_GROQ=
if exist "%APP_DIR%\.env" (
    for /f "tokens=2 delims==" %%a in ('findstr "TRANSCRIRE_GEMINI_API_KEY" "%APP_DIR%\.env"') do set EXISTING_GEMINI=%%a
    for /f "tokens=2 delims==" %%a in ('findstr "TRANSCRIRE_GROQ_API_KEY" "%APP_DIR%\.env"') do set EXISTING_GROQ=%%a
)

if "%EXISTING_GEMINI%"=="" (
    echo  Gemini key missing. Get one at:
    echo  https://aistudio.google.com/apikey
    echo.
    set /p GEMINI_KEY="  Paste your Gemini API key: "
) else (
    set GEMINI_KEY=%EXISTING_GEMINI%
)

if "%EXISTING_GROQ%"=="" (
    echo.
    echo  Groq key missing. Get one at:
    echo  https://console.groq.com
    echo.
    set /p GROQ_KEY="  Paste your Groq API key: "
) else (
    set GROQ_KEY=%EXISTING_GROQ%
)

echo TRANSCRIRE_GEMINI_API_KEY=%GEMINI_KEY%> "%APP_DIR%\.env"
echo TRANSCRIRE_GROQ_API_KEY=%GROQ_KEY%>> "%APP_DIR%\.env"
echo.
echo  Keys saved. Launching Transcrire...
echo.

:RUN
:: ---- Sync dependencies (fast no-op if nothing changed) ----
"%UV_EXE%" sync --frozen --quiet >nul 2>&1

:: ---- Launch ----
"%PYTHON%" -m transcrire

if errorlevel 1 (
    echo.
    echo  [ERROR] Transcrire encountered an error.
    echo  Check the log at: %APP_DIR%\transcrire.log
    pause
)
