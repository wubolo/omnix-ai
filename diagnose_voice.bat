@echo off
cd /d "%~dp0"
rem installed app: the Python that the installer downloaded sits one folder up
if exist "%~dp0..\python\python.exe" (
  "%~dp0..\python\python.exe" diagnose_voice.py
) else (
  if exist ".buildenv\Scripts\python.exe" (call ".buildenv\Scripts\activate.bat")
  python diagnose_voice.py
)
pause
