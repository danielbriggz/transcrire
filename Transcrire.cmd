@echo off
:: ============================================================
:: Transcrire — Installer & Launcher
:: Developer: Daniel "Briggz" Adisa
:: ============================================================
:: Double-click this file to install or launch Transcrire.
::
:: First run  — downloads and installs everything automatically
:: Every run  — launches Transcrire directly
:: ============================================================

title Transcrire

:: ============================================================
:: PATHS
:: APP_DIR  — where scripts and venv live (hidden from user)
:: USER_DIR — where input/ and output/ live (Desktop)
:: ============================================================
set APP_DIR=%APPDATA%\Transcrire
set USER_DIR=%USERPROFILE%\Desktop\Transcrire
set VENV=%APP_DIR%\.venv
set PYTHON=%VENV%\Scripts\python.exe
set REPO=https://github.com/danielbriggz/transcrire/archive/refs/heads/main.zip

echo.
echo  ============================================
echo         ^|^|^| TRANSCRIRE ^|^|^|
echo  ============================================
echo.

:: ============================================================
:: STEP 1: CHECK PYTHON IS INSTALLED
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
    echo  [WARNING] Python 3.13+ detected. Some audio features may not work correctly.
    echo  Recommended: Python 3.10-3.12
    echo.
    timeout /t 5 >nul
)

:: ============================================================
:: STEP 2: CREATE USER FOLDERS ON DESKTOP
:: These are the only folders the user sees and interacts with
:: ============================================================
if not exist "%USER_DIR%\input"  mkdir "%USER_DIR%\input"
if not exist "%USER_DIR%\output" mkdir "%USER_DIR%\output"

:: ============================================================
:: STEP 3: CHECK IF ALREADY INSTALLED
:: If venv exists, skip installation and launch directly
:: ============================================================
if exist "%PYTHON%" (
    echo  Transcrire already installed. Launching...
    goto LAUNCH
)

:: ============================================================
:: STEP 4: FIRST-TIME INSTALLATION
:: ============================================================
echo.
echo  First-time setup. This will take a few minutes.
echo  Please do not close this window.
echo.

:: ---- Create AppData directory ----
if not exist "%APP_DIR%" mkdir "%APP_DIR%"

:: ---- Download project from GitHub ----
echo  Downloading Transcrire...
curl -L -o "%APP_DIR%\transcrire.zip" "%REPO%"
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
:: GitHub zip extracts to a subfolder — move contents up one level
for /d %%i in ("%APP_DIR%\extracted\*") do (
    xcopy "%%i\*" "%APP_DIR%\" /E /I /Y >nul
)

:: ---- Clean up zip and temp folder ----
del "%APP_DIR%\transcrire.zip" >nul 2>&1
rmdir /s /q "%APP_DIR%\extracted" >nul 2>&1

:: ---- Create virtual environment ----
echo  Creating Python environment...
python -m venv "%VENV%"
if errorlevel 1 (
    echo.
    echo  [ERROR] Could not create virtual environment.
    pause
    exit /b 1
)

:: ---- Install dependencies ----
echo  Installing dependencies (this may take a few minutes)...
"%VENV%\Scripts\pip.exe" install --upgrade pip >nul 2>&1
"%VENV%\Scripts\pip.exe" install openai-whisper feedparser requests google-genai groq pillow plyer python-dotenv
if errorlevel 1 (
    echo.
    echo  [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

:: ---- Create .env file — prompt user for API keys ----
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

    :: Write keys to .env
    echo GEMINI_API_KEY=%GEMINI_KEY%> "%APP_DIR%\.env"
    echo GROQ_API_KEY=%GROQ_KEY%>> "%APP_DIR%\.env"

    echo  API keys saved.
    echo.
)

:: ---- Create config pointing to Desktop folders ----
:: Override input/output paths to point to Desktop/Transcrire
(
    echo INPUT_FOLDER = r"%USER_DIR%\input"
    echo OUTPUT_FOLDER = r"%USER_DIR%\output"
) > "%APP_DIR%\user_paths.py"

echo.
echo  ============================================
echo   Installation complete!
echo  ============================================
echo.
echo  Your files will be saved to:
echo  %USER_DIR%
echo.

:: ============================================================
:: STEP 5: LAUNCH
:: ============================================================
:LAUNCH
cd /d "%APP_DIR%"
call "%VENV%\Scripts\activate.bat"

:: ---- Pass all paths to the program via environment variables ----
:: TRANSCRIRE_APPDATA tells config.py where to find the .env file
:: TRANSCRIRE_INPUT and TRANSCRIRE_OUTPUT point to Desktop folders
set TRANSCRIRE_APPDATA=%APP_DIR%
set TRANSCRIRE_INPUT=%USER_DIR%\input
set TRANSCRIRE_OUTPUT=%USER_DIR%\output

"%PYTHON%" launch.py
if errorlevel 1 (
    echo.
    echo  [ERROR] Transcrire encountered an error.
    echo  Please check the output above for details.
    pause
)