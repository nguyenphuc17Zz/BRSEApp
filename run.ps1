Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "       AI COMTOR / BrSE COPILOT (PHASE 1)               " -ForegroundColor Cyan
Write-Host "     Local-First Translation & Knowledge Engine         " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$RootPath = $PSScriptRoot
Set-Location $RootPath

# 1. Start Backend in separate process
Write-Host "`n[1/2] Starting Backend API Service (http://127.0.0.1:8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$RootPath\services\backend'; .\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload"

Start-Sleep -Seconds 3

# 2. Open browser and start frontend
Write-Host "[2/2] Launching Web UI at http://127.0.0.1:5173..." -ForegroundColor Green
Start-Process "http://127.0.0.1:5173"

Set-Location "$RootPath\apps\web"
npm run dev
