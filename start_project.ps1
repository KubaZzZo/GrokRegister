param(
    [int]$Thread = 2,
    [switch]$NoSolverDebug,
    [switch]$OnlySolver,
    [switch]$OnlyMain
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Error "Virtual environment not found. Expected: $venvPython"
    exit 1
}

if ($OnlySolver -and $OnlyMain) {
    Write-Error "OnlySolver and OnlyMain cannot be used together."
    exit 1
}

$solverCommand = "Set-Location '$projectRoot'; & '$venvPython' api_solver.py --browser_type chromium --thread $Thread"
if (-not $NoSolverDebug) {
    $solverCommand += " --debug"
}

$solverArgs = @(
    "-NoExit",
    "-Command",
    $solverCommand
)

$mainArgs = @(
    "-NoExit",
    "-Command",
    "Set-Location '$projectRoot'; & '$venvPython' grok.py"
)

if (-not $OnlyMain) {
    Start-Process powershell -WorkingDirectory $projectRoot -ArgumentList $solverArgs
}

if (-not $OnlySolver) {
    if (-not $OnlyMain) {
        Start-Sleep -Seconds 2
    }
    Start-Process powershell -WorkingDirectory $projectRoot -ArgumentList $mainArgs
}

if ($OnlySolver) {
    Write-Host "Started api_solver.py in a separate PowerShell window."
} elseif ($OnlyMain) {
    Write-Host "Started grok.py in a separate PowerShell window."
} else {
    Write-Host "Started api_solver.py and grok.py in separate PowerShell windows."
}
