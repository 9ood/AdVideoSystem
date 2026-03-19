$ErrorActionPreference = "Stop"

$Targets = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "python.exe" -and
    $_.CommandLine -like "*AdVideoSystem*run_server.py*"
}

if (-not $Targets) {
    Write-Output "AdVideoSystem is not running"
    return
}

$Targets | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
}

Write-Output "AdVideoSystem stopped"
