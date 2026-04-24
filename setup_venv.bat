@echo off
REM ============================================================
REM  Hallucination Detection Middleware — Virtual Environment Setup
REM  Run this once to set up your Python environment.
REM  After setup: run start.bat to launch the server.
REM ============================================================

cd /d "%~dp0"

echo.
echo [1/5] Checking Python...
python --version
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from python.org
    pause
    exit /b 1
)

echo.
echo [2/5] Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

echo.
echo [3/5] Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo [4/5] Installing dependencies (this may take a few minutes)...
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 (
    echo WARNING: Some packages may have failed. Check output above.
)

echo.
echo [5/5] Downloading spaCy language model...
python -m spacy download en_core_web_sm
if errorlevel 1 (
    echo WARNING: spaCy model download failed. Sentence splitting will use fallback.
)

echo.
echo ============================================================
echo  Setup complete!
echo  Run start.bat to launch the server.
echo  GPU support: auto-detected (CUDA if NVIDIA GPU present)
echo ============================================================
echo.
pause
