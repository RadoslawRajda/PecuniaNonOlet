@echo off
setlocal
cd /d "%~dp0"

echo === PECUNIANONOLET BACKEND ===
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=py -3"
) else (
    set "PYTHON=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Tworzenie srodowiska Python...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)

echo Instalacja zaleznosci skryptu...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

".venv\Scripts\python.exe" launcher.py %*
if errorlevel 1 goto :error

echo.
pause
exit /b 0

:error
echo.
echo Nie udalo sie uruchomic projektu. Przeczytaj README.md.
pause
exit /b 1
