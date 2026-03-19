$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Python virtual environment not found: $PythonExe"
}

Push-Location $RepoRoot
try {
    & $PythonExe "run_server.py"
}
finally {
    Pop-Location
}
