Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   OrQuanta - Public Launch Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# --- Step 1: Check if server is already running ---
$serverUp = $false
try {
    $r = Invoke-WebRequest http://localhost:8000/health -UseBasicParsing -TimeoutSec 3
    $serverUp = $r.StatusCode -eq 200
} catch {}

if ($serverUp) {
    Write-Host "`n[1/2] OrQuanta server: ALREADY RUNNING on port 8000" -ForegroundColor Green
} else {
    Write-Host "`n[1/2] Starting OrQuanta server..." -ForegroundColor Yellow
    
    # Start server in a new window
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd c:\ai-gpu-cloud\v4; " +
        "`$env:ORQUANTA_DEMO_MODE='true'; " +
        "`$env:JWT_SECRET='orquanta-jwt-secret-2026'; " +
        "`$env:ADMIN_EMAIL='admin@orquanta.ai'; " +
        "`$env:ADMIN_PASSWORD='Secure123!'; " +
        "Write-Host 'OrQuanta API starting...' -ForegroundColor Cyan; " +
        "python -m uvicorn api.main:app --host 0.0.0.0 --port 8000"
    ) -WindowStyle Normal

    # Wait for it to be ready
    Write-Host "  Waiting for server to be ready" -NoNewline
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep 2
        try {
            $r = Invoke-WebRequest http://localhost:8000/health -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $serverUp = $true; break }
        } catch {}
        Write-Host "." -NoNewline
    }
    
    if ($serverUp) {
        Write-Host " READY!" -ForegroundColor Green
    } else {
        Write-Host " TIMEOUT - check the server window" -ForegroundColor Red
        Write-Host "Press any key to try the tunnel anyway..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    }
}

# --- Step 2: Start cloudflared tunnel ---
Write-Host "`n[2/2] Starting public HTTPS tunnel..." -ForegroundColor Yellow

$cfPaths = @(
    "C:\Program Files\cloudflared\cloudflared.exe",
    "C:\Program Files (x86)\cloudflared\cloudflared.exe"
)
$cfFromPath = Get-Command cloudflared -ErrorAction SilentlyContinue
if ($cfFromPath) { $cfPaths += $cfFromPath.Source }
$cfPaths = $cfPaths | Where-Object { $_ -and (Test-Path $_) }

$cfExe = $cfPaths | Select-Object -First 1

if (-not $cfExe) {
    Write-Host "cloudflared.exe not found! Installing..." -ForegroundColor Red
    winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
    $cfExe = "C:\Program Files\cloudflared\cloudflared.exe"
}

Write-Host "  Using: $cfExe" -ForegroundColor Gray
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Your PUBLIC URL will appear below:" -ForegroundColor Cyan  
Write-Host " Look for: https://xxxx.trycloudflare.com" -ForegroundColor Green
Write-Host " Copy that URL - it's your shareable link!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Start tunnel - output goes directly to console
& $cfExe tunnel --url http://localhost:8000
