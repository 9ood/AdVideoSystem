$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$LogsDir = Join-Path $RepoRoot "logs"
$OutLog = Join-Path $LogsDir "dashboard-server.out.log"
$ErrLog = Join-Path $LogsDir "dashboard-server.err.log"

if (-not (Test-Path $PythonExe)) {
    throw "Python virtual environment not found: $PythonExe"
}

$Existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "python.exe" -and
    $_.CommandLine -like "*AdVideoSystem*run_server.py*"
}

if ($Existing) {
    Write-Output "AdVideoSystem is already running"
    return
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$Process = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList "run_server.py" `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Write-Output "AdVideoSystem started. PID: $($Process.Id)"
