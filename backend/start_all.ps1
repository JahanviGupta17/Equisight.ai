# start_all.ps1
# Starts all Equisight.ai services for local development.
# Run from the project root: .\start_all.ps1

Write-Host "Starting Equisight.ai services..." -ForegroundColor Cyan

# 1. Redis
Write-Host "[1/3] Starting Redis (Using stable config to prevent Windows crash)..." -ForegroundColor Yellow
Start-Process -FilePath "redis\redis-server.exe" -ArgumentList "redis\redis.stable.conf" -WindowStyle Minimized
Start-Sleep -Seconds 2
$ping = .\redis\redis-cli.exe ping
if ($ping -eq "PONG") {
    Write-Host "      Redis is UP." -ForegroundColor Green
} else {
    Write-Host "      Redis did not respond. Check redis\redis-server.exe." -ForegroundColor Red
}

# 2. Celery Worker
Write-Host "[2/3] Starting Celery Worker..." -ForegroundColor Yellow
Start-Process -FilePath ".venv\Scripts\celery.exe" `
    -ArgumentList "-A app.worker.celery_app worker --loglevel=info --pool=solo" `
    -WindowStyle Normal
Write-Host "      Celery Worker window opened." -ForegroundColor Green

# 3. Celery Beat
Write-Host "[3/3] Starting Celery Beat Scheduler..." -ForegroundColor Yellow
Start-Process -FilePath ".venv\Scripts\celery.exe" `
    -ArgumentList "-A app.worker.celery_app beat --loglevel=info" `
    -WindowStyle Normal
Write-Host "      Celery Beat window opened." -ForegroundColor Green

Write-Host ""
Write-Host "All background services are running!" -ForegroundColor Cyan
Write-Host "Now start the API server with:" -ForegroundColor White
Write-Host "  .venv\Scripts\uvicorn app.main:app --reload" -ForegroundColor White
Write-Host ""
Write-Host "Swagger UI: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
