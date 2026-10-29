@echo off
chcp 65001 >nul
cd /d "%~dp0"
set URL=https://models.silero.ai/models/tts/ru/v5_5_ru.pt
set OUT=%~dp0models\v5_5_ru.pt
if not exist models mkdir models
del "%USERPROFILE%\.cache\torch\hub\silero\v5_5_ru.pt" >nul 2>&1
del "%OUT%" >nul 2>&1

echo [1/4] Синхронизация времени Windows (нужны права администратора, иначе пропустится)...
w32tm /resync >nul 2>&1

echo [2/4] Скачивание через curl (системные сертификаты Windows)...
curl.exe -L --fail -o "%OUT%" "%URL%"
call :check && goto ok

echo [3/4] Скачивание через PowerShell...
powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol='Tls12,Tls13'; Invoke-WebRequest -Uri '%URL%' -OutFile '%OUT%' } catch { Write-Host $_.Exception.Message }"
call :check && goto ok

echo [4/4] Скачивание через Python (certifi)...
python -c "import requests,sys; r=requests.get('%URL%',stream=True,timeout=60); r.raise_for_status(); f=open(r'%OUT%','wb'); [f.write(c) for c in r.iter_content(1<<20)]; f.close()"
call :check && goto ok

echo.
echo НЕ УДАЛОСЬ. Скачайте файл в браузере вручную:
echo   %URL%
echo и положите его сюда: %OUT%
echo (проверка сертификатов нигде не отключалась)
pause
exit /b 1

:ok
echo.
echo Готово: модель лежит в %OUT%
echo Теперь запускайте программу как обычно.
pause
exit /b 0

:check
if not exist "%OUT%" exit /b 1
python -c "import zipfile,sys; z=zipfile.ZipFile(r'%OUT%'); sys.exit(0 if z.testzip() is None else 1)" >nul 2>&1
if errorlevel 1 (del "%OUT%" >nul 2>&1 & exit /b 1)
exit /b 0
