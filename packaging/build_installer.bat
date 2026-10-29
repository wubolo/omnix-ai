@echo off
setlocal
cd /d "%~dp0\..\..\..\.."
set "NSIS=C:\Program Files (x86)\NSIS\makensis.exe"
if not exist "%NSIS%" set "NSIS=C:\Program Files\NSIS\makensis.exe"
if not exist "%NSIS%" (
  echo NSIS was not found. Install it with: winget install --id NSIS.NSIS -e
  exit /b 1
)
if not exist "outputs\AICompanion.exe" (
  echo Build outputs\AICompanion.exe first.
  exit /b 1
)
"%NSIS%" "work\project\AI-Companion\packaging\portable_installer.nsi"
if errorlevel 1 exit /b 1
echo Created: %CD%\outputs\AICompanion-Setup.exe
