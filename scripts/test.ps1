$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Python virtual environment not found: $PythonExe"
}

& $PythonExe -m py_compile `
    (Join-Path $RepoRoot "app.py") `
    (Join-Path $RepoRoot "ai_analyzer.py") `
    (Join-Path $RepoRoot "excel_generator.py") `
    (Join-Path $RepoRoot "video_processor.py") `
    (Join-Path $RepoRoot "run_server.py")

@'
from ai_analyzer import PRODUCT_IMAGE_MAPPING
missing = [path for path in PRODUCT_IMAGE_MAPPING.values() if not __import__('os').path.exists(path)]
if missing:
    raise SystemExit("Missing resource images: " + ", ".join(missing))
print("resource image mapping ok")
'@ | & $PythonExe -

Write-Output "AdVideoSystem test passed"
