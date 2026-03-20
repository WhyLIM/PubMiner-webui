$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$backendDir = Join-Path $projectRoot "PubMiner"
$apiScript = Join-Path $backendDir "api_server.py"
$port = 8000

if (-not (Test-Path $venvPython)) {
    Write-Error "Project virtual environment was not found at $venvPython"
}

if (-not (Test-Path $apiScript)) {
    Write-Error "Backend entry point was not found at $apiScript"
}

$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-Warning "Port $port is already in use by PID $($listener.OwningProcess). Stop that process before starting a new backend."
    exit 1
}

Write-Host "Using Python:" $venvPython
Write-Host "Starting PubMiner backend on http://localhost:$port ..."

Push-Location $backendDir
try {
    & $venvPython $apiScript
}
finally {
    Pop-Location
}
