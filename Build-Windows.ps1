$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    $geoTraceBuildTarget = Join-Path $PSScriptRoot 'dist\GeoTrace\GeoTrace.exe'
    $geoTraceRunning = Get-Process -Name GeoTrace -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $geoTraceBuildTarget }
    if ($geoTraceRunning) { throw 'Close GeoTrace before building; the running portable application will not be overwritten.' }
    python -m pip install -e '.[test,build]'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    python -m PyInstaller --clean --noconfirm --windowed --name GeoTrace --collect-data tzdata launch.py
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    Write-Output "Application: $PSScriptRoot\dist\GeoTrace\GeoTrace.exe"
} finally { Pop-Location }
