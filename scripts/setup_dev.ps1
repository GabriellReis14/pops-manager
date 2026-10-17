<#
.SYNOPSIS
    Creates .venv and installs POPS Manager in editable mode with dev tools (pytest, PyInstaller).
    Uses uv when available, otherwise the Python launcher (py) / python.
#>
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    $Python = '.venv\Scripts\python.exe'
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        if (-not (Test-Path $Python)) { uv venv .venv --python '>=3.10' }
        uv pip install --python $Python -e '.[dev]'
    } else {
        if (-not (Test-Path $Python)) {
            if (Get-Command py -ErrorAction SilentlyContinue) { py -3 -m venv .venv } else { python -m venv .venv }
        }
        & $Python -m pip install --upgrade pip
        & $Python -m pip install -e '.[dev]'
    }
    if ($LASTEXITCODE) { throw 'Dependency installation failed.' }
    & $Python --version
}
finally { Pop-Location }
