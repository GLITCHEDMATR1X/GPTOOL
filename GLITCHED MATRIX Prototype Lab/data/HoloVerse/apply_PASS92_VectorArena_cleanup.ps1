param(
    [string]$ProjectRoot = $PSScriptRoot
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path $ProjectRoot
$targets = @(
    "Dimensions/HoloUtopia",
    "Dimensions/Etch-Line",
    "logs/latest.log",
    "logs/mode_gateway_audit.json",
    "logs/mode_gateway_history.json"
)

foreach ($target in $targets) {
    $path = Join-Path $root $target
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
        Write-Host "Removed $target"
    }
}

Get-ChildItem -LiteralPath $root -Directory -Recurse -Force -Filter "__pycache__" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
}
Get-ChildItem -LiteralPath $root -File -Recurse -Force -Include "*.pyc" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Force
}

Write-Host "Pass 92 cleanup complete. Vector Arena is the built-in slot-1 dimension."
