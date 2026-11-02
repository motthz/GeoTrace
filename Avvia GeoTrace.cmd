@echo off
if exist "%~dp0dist\GeoTrace\GeoTrace.exe" (
    start "" "%~dp0dist\GeoTrace\GeoTrace.exe"
) else (
    echo Eseguibile non trovato. Eseguire Build-Windows.ps1 per preparare GeoTrace.
    pause
)
