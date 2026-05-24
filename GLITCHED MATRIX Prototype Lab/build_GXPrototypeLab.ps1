param(
    [switch]$Full,
    [switch]$ZipDist,
    [switch]$IncludeGames
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$ReleaseJunkDirNames = @(
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env",
    "crash_reports", "screenshots"
)

$ReleaseJunkFilePatterns = @(
    "*.pyc", "*.pyo", "*.tmp", "*.temp", "*.bak", "*.orig",
    "*.log", "latest*.txt", "*_smoke.png", "*_smoke_report.json",
    "mode_gateway_*.json", "self_test_report.json", "runtime_integration_smoke_report.json",
    "world_authority_smoke.png", "world_authority_smoke_report.json",
    "bridge_exit_cleanup_auto.json", "bridge_exit_cleanup_auto.png"
)

function Remove-ReleaseJunk {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Path
    )

    if (!(Test-Path $Path)) { return }

    foreach ($Name in $ReleaseJunkDirNames) {
        Get-ChildItem -LiteralPath $Path -Directory -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ieq $Name } |
            Sort-Object FullName -Descending |
            ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
            }
    }

    # Most logs are runtime/test debris. Keep the single roadmap status file.
    Get-ChildItem -LiteralPath $Path -Directory -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ieq "logs" } |
        Sort-Object FullName -Descending |
        ForEach-Object {
            $Roadmap = Join-Path $_.FullName "ROADMAP_STATUS.md"
            if (Test-Path $Roadmap) {
                $TempRoadmap = Join-Path ([System.IO.Path]::GetTempPath()) ("GX_ROADMAP_STATUS_" + [guid]::NewGuid().ToString() + ".md")
                Copy-Item -LiteralPath $Roadmap -Destination $TempRoadmap -Force
                Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
                New-Item -ItemType Directory -Force -Path $_.FullName | Out-Null
                Copy-Item -LiteralPath $TempRoadmap -Destination $Roadmap -Force
                Remove-Item -LiteralPath $TempRoadmap -Force -ErrorAction SilentlyContinue
            } else {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

    foreach ($Pattern in $ReleaseJunkFilePatterns) {
        Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction SilentlyContinue -Filter $Pattern |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
    }

    # Final guard against the old accidental data/data lane.
    $NestedData = Join-Path $Path "data\data"
    if (Test-Path $NestedData) {
        Remove-Item -LiteralPath $NestedData -Recurse -Force -ErrorAction SilentlyContinue
    }
    $InternalNestedData = Join-Path $Path "_internal\data\data"
    if (Test-Path $InternalNestedData) {
        Remove-Item -LiteralPath $InternalNestedData -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Assert-SteamReadyTree {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Path
    )

    $ForbiddenDirs = Get-ChildItem -LiteralPath $Path -Directory -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object {
            $n = $_.Name.ToLowerInvariant()
            $n -in @("__pycache__", ".venv", "venv", "env", "crash_reports", "screenshots") -or
            ($n -eq "logs" -and !(Test-Path (Join-Path $_.FullName "ROADMAP_STATUS.md")))
        }
    if ($ForbiddenDirs) {
        $List = ($ForbiddenDirs | Select-Object -First 20 | ForEach-Object { $_.FullName }) -join "`n"
        throw "Steam-ready tree still contains forbidden runtime/dev directories:`n$List"
    }

    $ForbiddenFiles = Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @(".pyc", ".pyo", ".log", ".tmp", ".bak") }
    if ($ForbiddenFiles) {
        $List = ($ForbiddenFiles | Select-Object -First 20 | ForEach-Object { $_.FullName }) -join "`n"
        throw "Steam-ready tree still contains forbidden runtime/dev files:`n$List"
    }

    if ((Test-Path (Join-Path $Path "data")) -and (Test-Path (Join-Path $Path "_internal\data"))) {
        throw "Steam-ready tree contains duplicate root data and _internal data folders. The packaged app should use one authoritative bundled data tree."
    }
    if ((Test-Path (Join-Path $Path "assets")) -and (Test-Path (Join-Path $Path "_internal\assets"))) {
        throw "Steam-ready tree contains duplicate root assets and _internal assets folders. The packaged app should use one authoritative bundled assets tree."
    }
}

function Invoke-Step {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Label,
        [Parameter(Mandatory=$true)]
        [scriptblock]$Action
    )

    Write-Host "==> $Label"
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

$Venv = Join-Path $Root ".venv_build"
if (!(Test-Path $Venv)) {
    & py -3.13 -m venv $Venv
    if (!(Test-Path $Venv)) {
        & py -3 -m venv $Venv
    }
    if (!(Test-Path $Venv)) {
        & python -m venv $Venv
    }
}

$Py = Join-Path $Venv "Scripts\python.exe"
if (!(Test-Path $Py)) {
    throw "Build venv did not create a usable Python executable: $Py"
}
Invoke-Step "Upgrade build tools" { & $Py -m pip install --upgrade pip wheel setuptools pyinstaller }

$RequirementsFile = Join-Path $Root "requirements.txt"
if (!(Test-Path $RequirementsFile)) {
    throw "requirements.txt is required for a reproducible portable build, but it is missing from: $Root"
}

Invoke-Step "Install portable runtime requirements" { & $Py -m pip install -r $RequirementsFile }
Invoke-Step "Verify launcher/game runtime imports" {
    & $Py -c "import tkinter, _tkinter; import pygame; import panda3d; import direct.showbase.ShowBase; import PIL.Image, PIL.ImageTk; import numpy; import mss; import pydub; import reportlab; import trimesh; import cv2; import tkinterdnd2; print('GX runtime import set OK')"
}

if ($Full) {
    Invoke-Step "Install full optional packages" { & $Py -m pip install pyqt6 pyside6 opencv-python }
}

if (Test-Path (Join-Path $Root "dist")) { Remove-Item (Join-Path $Root "dist") -Recurse -Force }
if (Test-Path (Join-Path $Root "build")) { Remove-Item (Join-Path $Root "build") -Recurse -Force }

# GXPrototypeLab.spec snapshots assets/data through a clean-tree collector, so
# source folders are not mutated just to prepare a release build.
Invoke-Step "Build py_runner" { & $Py -m PyInstaller --noconfirm --clean py_runner.spec }
Invoke-Step "Build GXPrototypeLab" { & $Py -m PyInstaller --noconfirm --clean GXPrototypeLab.spec }

$DistRoot = Join-Path $Root "dist\GXPrototypeLab"
New-Item -ItemType Directory -Force -Path $DistRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DistRoot "py_runner") | Out-Null

$RunnerBuiltDir = Join-Path $Root "dist\py_runner"
if (Test-Path $RunnerBuiltDir) {
    Copy-Item (Join-Path $RunnerBuiltDir "*") (Join-Path $DistRoot "py_runner") -Recurse -Force
}

# Do not copy assets/ or data/ beside the EXE. PyInstaller already places the
# authoritative bundled copies under _internal. Duplicating them at the dist root
# bloats the Steam depot and can make the app read/write the wrong tree.
$CopyItems = @(
    "desktop_settings.json",
    "folder_list.txt",
    "launcher_logo.png",
    "README_BUILD_EXE.md"
)

foreach ($Item in $CopyItems) {
    $Source = Join-Path $Root $Item
    if (Test-Path $Source) {
        Copy-Item $Source $DistRoot -Recurse -Force
    }
}

if ($IncludeGames -and (Test-Path (Join-Path $Root "games"))) {
    Copy-Item (Join-Path $Root "games") $DistRoot -Recurse -Force
}

$RunnerIntermediate = Join-Path $Root "dist\py_runner"
if (Test-Path $RunnerIntermediate) {
    Remove-Item -LiteralPath $RunnerIntermediate -Recurse -Force -ErrorAction SilentlyContinue
}

Remove-ReleaseJunk -Path $DistRoot
Assert-SteamReadyTree -Path $DistRoot

$BuildWork = Join-Path $Root "build"
if (Test-Path $BuildWork) {
    Remove-Item -LiteralPath $BuildWork -Recurse -Force -ErrorAction SilentlyContinue
}

if ($ZipDist) {
    $ZipPath = Join-Path $Root "GXPrototypeLab_dist.zip"
    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    Compress-Archive -Path (Join-Path $DistRoot "*") -DestinationPath $ZipPath
    Write-Host "Created $ZipPath"
}

Write-Host "Build complete: $DistRoot"
