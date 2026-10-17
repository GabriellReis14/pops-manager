# Runs POPS Manager from source (works from any current directory).
$Python = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw "Missing .venv. Run: .\scripts\setup_dev.ps1" }
& $Python -m pops_manager @args
