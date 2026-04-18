# Build a standalone `pca.exe` on Windows.
#
#   PS> .\packaging\build_exe.ps1
#
# Run from the repo root. Produces dist\pca.exe (single-file).

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv ..."
    python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .\.venv\Scripts\python.exe -m pip install -e ".[packaging,web,gui]" | Out-Null

Write-Host "Building pca.exe (CLI) ..."
& .\.venv\Scripts\python.exe -m PyInstaller packaging\pca.spec --clean --noconfirm

Write-Host "Building pca-gui.exe (native GUI) ..."
& .\.venv\Scripts\python.exe -m PyInstaller packaging\pca-gui.spec --clean --noconfirm

Write-Host ""
Write-Host "Built:"
Write-Host ("  CLI: {0} ({1:n1} MB)" -f (Resolve-Path 'dist\pca.exe'), ((Get-Item 'dist\pca.exe').Length / 1MB))
Write-Host ("  GUI: {0} ({1:n1} MB)" -f (Resolve-Path 'dist\pca-gui.exe'), ((Get-Item 'dist\pca-gui.exe').Length / 1MB))
Write-Host ""
Write-Host "Smoke: pca --help"
& .\dist\pca.exe --help | Select-Object -First 3
