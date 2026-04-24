@echo off
REM ============================================================
REM  Hallucination Detection System — Single-command startup
REM ============================================================

echo.
echo  Starting Hallucination Detection System...
echo  Backend  : http://localhost:8080
echo  Frontend : http://localhost:8080  (served by FastAPI)
echo  Dev UI   : http://localhost:5173  (optional, run separately)
echo.

cd /d "%~dp0"

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
    echo  [venv activated]
)

REM Load .env if present
if exist .env (
    for /f "tokens=1,2 delims==" %%a in (.env) do (
        if not "%%a"=="" if not "%%b"=="" set %%a=%%b
    )
)

python run_proxy.py %*
