$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    python -m pip install -e '.[test,build]'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    python -m PyInstaller --noconfirm --windowed --name GeoTrace --collect-data tzdata launch.py
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    Write-Output "Application: $PSScriptRoot\dist\GeoTrace\GeoTrace.exe"
} finally { Pop-Location }
