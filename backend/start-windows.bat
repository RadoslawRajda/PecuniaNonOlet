@echo off
setlocal
cd /d "%~dp0"

echo === PECUNIANONOLET BACKEND ===
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=py -3.11"
) else (
    set "PYTHON=python"
)

%PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo Wymagany jest Python 3.11 lub nowszy.
    goto :error
)

if not exist ".venv\Scripts\python.exe" (
    echo Tworzenie srodowiska Python...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)

echo Instalacja zaleznosci skryptu...
".venv\Scripts\python.exe" -m pip install -r requirements-runtime.lock.txt
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
