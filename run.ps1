$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$existing = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
  Start-Process "http://127.0.0.1:8000/"
  Write-Host "Port 8000 is already in use. Opened the existing server."
  return
}
Start-Process "http://127.0.0.1:8000/"
python server.py --host 127.0.0.1 --port 8000
