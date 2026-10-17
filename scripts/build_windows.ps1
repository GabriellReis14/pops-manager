<#
.SYNOPSIS
    Builds the portable (onedir) Windows version of POPS Manager into dist\POPS-Manager\.
.DESCRIPTION
    Public build (default): no POPStarter files inside. Users put theirs in dist\POPS-Manager\resources\
    or select them in Settings.

    Personal build (-BundleResources): embeds YOUR POPSTARTER.ELF, POPS_IOX.PAK and POPSTARTER folder
    in the exe so nothing has to be selected. Those files are third-party/proprietary (POPS_IOX.PAK
    contains Sony's emulator): never publish or share a personal build.
.EXAMPLE
    .\scripts\build_windows.ps1                     # tests + public build + smoke test
    .\scripts\build_windows.ps1 -SkipTests
    .\scripts\build_windows.ps1 -Zip                # also dist\POPS-Manager-<version>-win64.zip
    .\scripts\build_windows.ps1 -BundleResources    # personal build, files from the project root
    .\scripts\build_windows.ps1 -BundleResources -ResourcesDir D:\ps2\popstarter
#>
param([switch]$SkipTests, [switch]$Zip, [switch]$BundleResources, [string]$ResourcesDir)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw "Missing .venv. Run: .\scripts\setup_dev.ps1" }

if ($BundleResources -and $Zip) { throw 'A personal build (-BundleResources) must not be zipped for distribution.' }
if (-not $ResourcesDir) { $ResourcesDir = $Root }
$Bundle = @()
$Stage = $null
if ($BundleResources) {
    # Same layout as the device root: POPS\ (POPSTARTER.ELF, POPS_IOX.PAK, CHEATS.TXT, IGR_*.TM2...) and POPSTARTER\
    $Pops = Join-Path $ResourcesDir 'POPS'
    $Support = Join-Path $ResourcesDir 'POPSTARTER'
    foreach ($item in (Join-Path $Pops 'POPSTARTER.ELF'), (Join-Path $Pops 'POPS_IOX.PAK'), $Support) {
        if (-not (Test-Path $item)) { throw "Missing $item" }
    }
    # Windows programs (the old converters and their DLLs) and game images are never embedded.
    $skip = '.exe', '.dll', '.vcd', '.bin', '.cue', '.iso', '.img', '.zip', '.7z'
    foreach ($file in Get-ChildItem $Pops -File | Where-Object { $skip -notcontains $_.Extension.ToLower() }) {
        $Bundle += @('--add-data', "$($file.FullName);resources\POPS")
    }
    $Bundle += @('--add-data', "$Support;resources\POPSTARTER")
    # Fix pack (POPSUtils): staged with short paths and without image patches (scripts/stage_fixes.py)
    $Utils = Join-Path $Pops 'POPSUtils'
    if (Test-Path $Utils) {
        $Stage = Join-Path $Root 'build\resources_stage\POPSUtils'
        & $Python (Join-Path $PSScriptRoot 'stage_fixes.py') $Utils $Stage
        if ($LASTEXITCODE) { throw "Could not stage $Utils" }
        $Bundle += @('--add-data', "$Stage;resources\POPS\POPSUtils")
    }
    Write-Warning 'PERSONAL BUILD: embeds third-party POPStarter/Sony files. Do not publish or share it.'
}

Push-Location $Root
try {
    if (-not $SkipTests) {
        & $Python -m pytest -q
        if ($LASTEXITCODE) { throw 'Tests failed; build aborted.' }
    }

    & $Python -m PyInstaller --noconfirm --clean --onedir --windowed `
        --name POPS-Manager --paths "$Root\src" @Bundle `
        --distpath "$Root\dist" --workpath "$Root\build\pyinstaller" --specpath "$Root\build" `
        "$Root\src\pops_manager\__main__.py"
    if ($LASTEXITCODE) { throw 'PyInstaller failed.' }

    $App = Join-Path $Root 'dist\POPS-Manager'
    $Exe = Join-Path $App 'POPS-Manager.exe'
    foreach ($qm in 'qtbase_pt_BR.qm', 'qtbase_es.qm') {
        if (-not (Get-ChildItem $App -Recurse -Filter $qm)) { throw "Translation $qm missing from build." }
    }
    Copy-Item README.md, LICENSE $App
    $LocalRes = New-Item -ItemType Directory -Force (Join-Path $App 'resources')
    @(
        'Optional: put your own POPStarter files here (same layout as the USB root):',
        '  resources\POPS\POPSTARTER.ELF',
        '  resources\POPS\POPS_IOX.PAK',
        '  resources\POPSTARTER\...   (copied as-is to <USB>\POPSTARTER\)',
        'They can also be selected in Settings > POPStarter files.'
    ) | Set-Content (Join-Path $LocalRes 'README.txt') -Encoding utf8
    if ($BundleResources) {
        'Personal build with embedded third-party files. Do not distribute.' |
            Set-Content (Join-Path $App 'PERSONAL_BUILD_DO_NOT_DISTRIBUTE.txt') -Encoding utf8
    } else {
        Remove-Item (Join-Path $App 'PERSONAL_BUILD_DO_NOT_DISTRIBUTE.txt') -ErrorAction SilentlyContinue
    }

    # The exe is a GUI app: run it hidden (offscreen) and wait for its exit code.
    $env:QT_QPA_PLATFORM = 'offscreen'
    $smokeArgs = @('--smoke-test') + $(if ($BundleResources) { @('--expect-bundled') } else { @() })
    if ($BundleResources -and $Stage) { $smokeArgs += '--expect-fixes' }
    $proc = Start-Process $Exe -ArgumentList $smokeArgs -PassThru -Wait
    Remove-Item Env:QT_QPA_PLATFORM
    if ($proc.ExitCode -ne 0) { throw "Smoke test failed (exit code $($proc.ExitCode))." }

    $size = (Get-ChildItem $App -Recurse | Measure-Object Length -Sum).Sum / 1MB
    Write-Host ("OK: {0} ({1:N0} MB) - smoke test passed" -f $Exe, $size) -ForegroundColor Green

    if ($Zip) {
        $version = (& $Python -c "import importlib.metadata as m; print(m.version('community-pops-manager'))").Trim()
        $archive = Join-Path $Root "dist\POPS-Manager-$version-win64.zip"
        Compress-Archive -Path $App -DestinationPath $archive -Force
        Write-Host "ZIP: $archive"
    }
}
finally { Pop-Location }
