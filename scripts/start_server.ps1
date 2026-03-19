$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPath = Join-Path $RepoRoot ".venv"
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
$LogsDir = Join-Path $RepoRoot "logs"
$ToolsDir = Join-Path $RepoRoot "tools"
$FfmpegRoot = Join-Path $ToolsDir "ffmpeg"
$FfmpegZip = Join-Path $ToolsDir "ffmpeg-release-essentials.zip"
$FfmpegBin = $null
$ServerLog = Join-Path $LogsDir "server.log"
$SupervisorLog = Join-Path $LogsDir "supervisor.log"

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

function Write-SupervisorLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $SupervisorLog -Value $line
}

if (-not (Test-Path $PythonExe)) {
    Write-SupervisorLog "Creating virtual environment."
    py -3 -m venv $VenvPath
}

if (-not (Test-Path $PythonExe)) {
    throw "Virtual environment was not created successfully."
}

if (-not (Test-Path (Join-Path $RepoRoot ".env"))) {
    Copy-Item (Join-Path $RepoRoot ".env.example") (Join-Path $RepoRoot ".env")
    Write-SupervisorLog "Created .env from template."
}

Write-SupervisorLog "Installing Python dependencies."
& $PythonExe -m pip install --upgrade pip | Out-Null
& $PythonExe -m pip install -r (Join-Path $RepoRoot "requirements.txt")

if (-not (Test-Path $FfmpegRoot)) {
    Write-SupervisorLog "Downloading ffmpeg."
    Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $FfmpegZip
    Expand-Archive -Path $FfmpegZip -DestinationPath $ToolsDir -Force
    $Extracted = Get-ChildItem -Path $ToolsDir -Directory | Where-Object { $_.Name -like "ffmpeg-*-essentials_build" } | Select-Object -First 1
    if ($Extracted) {
        Rename-Item -Path $Extracted.FullName -NewName "ffmpeg" -Force
    }
}

if (Test-Path $FfmpegRoot) {
    $FfmpegBin = Join-Path $FfmpegRoot "bin"
}

Push-Location $RepoRoot
try {
    while ($true) {
        if ($FfmpegBin) {
            $env:PATH = "$FfmpegBin;$env:PATH"
        }

        Write-SupervisorLog "Starting server."
        & $PythonExe (Join-Path $RepoRoot "run_server.py") *>> $ServerLog
        $ExitCode = $LASTEXITCODE
        Write-SupervisorLog "Server stopped with exit code $ExitCode. Restarting in 5 seconds."
        Start-Sleep -Seconds 5
    }
}
finally {
    Pop-Location
}
