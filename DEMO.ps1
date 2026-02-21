# OrQuanta Golden Demo - One Command Execution
# Run this before client joins to ensure clean state

Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host "=" * 58 -ForegroundColor Cyan
Write-Host " OrQuanta Demo Preparation" -ForegroundColor White
Write-Host "=" * 59 -ForegroundColor Cyan

# Step 1: Reset to baseline
Write-Host "`n[1/3] Resetting to baseline state..." -ForegroundColor Yellow
$headers = @{
    "X-API-Key" = "dev-key-change-in-production"
    "Content-Type" = "application/json"
}
try {
    Invoke-RestMethod -Uri "http://localhost:8000/api/v1/reset" -Method POST -Headers $headers -Body "{}" | Out-Null
    Write-Host "      ✓ System reset to v1" -ForegroundColor Green
} catch {
    Write-Host "      ✗ Reset failed - is the server running?" -ForegroundColor Red
    exit 1
}

Start-Sleep -Seconds 1

# Step 2: Verify baseline
Write-Host "`n[2/3] Verifying baseline policy..." -ForegroundColor Yellow
$policy = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/policy" -Headers $headers
if ($policy.version -eq 1) {
    Write-Host "      ✓ Policy v1 confirmed" -ForegroundColor Green
    Write-Host "      ✓ Weights: cost=$($policy.weights.cost), perf=$($policy.weights.perf), risk=$($policy.weights.risk)" -ForegroundColor Green
} else {
    Write-Host "      ✗ Unexpected version: $($policy.version)" -ForegroundColor Red
    exit 1
}

# Step 3: Health check
Write-Host "`n[3/3] Final health check..." -ForegroundColor Yellow
$health = Invoke-RestMethod -Uri "http://localhost:8000/health"
Write-Host "      ✓ Status: $($health.status)" -ForegroundColor Green

Write-Host "`n" -NoNewline
Write-Host "=" * 59 -ForegroundColor Cyan
Write-Host " READY FOR DEMO" -ForegroundColor Green -BackgroundColor Black
Write-Host "=" * 59 -ForegroundColor Cyan

Write-Host "`nOpen in browser: " -NoNewline -ForegroundColor White
Write-Host "http://localhost:8000/docs" -ForegroundColor Cyan

Write-Host "`nRun demo script: " -NoNewline -ForegroundColor White
Write-Host "python DEMO_SCRIPT.py" -ForegroundColor Cyan
Write-Host ""
