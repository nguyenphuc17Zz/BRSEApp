@echo off
title AI Comtor / BrSE Copilot
echo ========================================================
echo        AI COMTOR / BrSE COPILOT (PHASE 1 - 4)
echo      BrSE Brain ^& Smart Workflow Automation
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/3] Checking Backend Environment...
if not exist "services\backend\.venv" (
    echo Creating Python virtual environment...
    python -m venv services\backend\.venv
    call services\backend\.venv\Scripts\pip.exe install -r services\backend\requirements.txt
)

echo [2/3] Starting Backend API Service on http://127.0.0.1:8000 ...
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if errorlevel 1 (
    start "Comtor Copilot Backend" cmd /k "cd services\backend && .venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload"
    timeout /t 3 /nobreak >nul
) else (
    echo Backend already active on port 8000.
)

echo [3/3] Starting Web UI on http://localhost:5173 ...
netstat -ano | findstr ":5173" | findstr "LISTENING" >nul
if errorlevel 1 (
    start "" http://localhost:5173
    cd apps\web
    npm run dev
) else (
    echo Web UI already active on port 5173.
    start "" http://localhost:5173
)

pause
