# OrQuanta — One-Click Server Starter
# Double-click this file to start the platform, then open http://localhost:8000/demo

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║       OrQuanta Agentic v1.0              ║" -ForegroundColor Cyan
Write-Host "  ║   Starting server on port 8000...        ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Change to project dir
Set-Location $PSScriptRoot

# Activate venv if it exists
if (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
    Write-Host "  [OK] Virtual environment activated" -ForegroundColor Green
}

# Check uvicorn is available
$uvicorn = python -c "import uvicorn; print('ok')" 2>$null
if ($uvicorn -ne "ok") {
    Write-Host "  [!] Installing dependencies..." -ForegroundColor Yellow
    pip install -r v4/requirements.txt -q
}

Write-Host ""
Write-Host "  Demo page  -->  http://localhost:8000/demo" -ForegroundColor Green
Write-Host "  Dashboard  -->  http://localhost:8000/app" -ForegroundColor Green
Write-Host "  API docs   -->  http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "  Press Ctrl+C to stop the server." -ForegroundColor DarkGray
Write-Host ""

# Open demo in default browser after 3-second delay
Start-Job -ScriptBlock {
    Start-Sleep 4
    Start-Process "http://localhost:8000/demo"
} | Out-Null

# Start the server
python -m uvicorn v4.api.main:app --host 0.0.0.0 --port 8000 --reload
