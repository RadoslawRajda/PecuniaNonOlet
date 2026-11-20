@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === PECUNIANONOLET BACKEND ===
set "PYTHON="
where py >nul 2>nul
if not errorlevel 1 (
    for %%V in (3.13 3.12 3.11) do (
        if not defined PYTHON (
            py -%%V -c "import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] <= (3, 13)))" >nul 2>nul
            if not errorlevel 1 set "PYTHON=py -%%V"
        )
    )
)
if not defined PYTHON (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] <= (3, 13)))" >nul 2>nul
        if not errorlevel 1 set "PYTHON=python"
    )
)
if not defined PYTHON (
    echo Wymagany jest Python 3.11, 3.12 lub 3.13.
    goto :error
)

if not exist ".venv\Scripts\python.exe" (
    echo Tworzenie srodowiska Python...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -c "import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] <= (3, 13)))" >nul 2>nul
if errorlevel 1 (
    echo Istniejace .venv uzywa niewspieranego Pythona lub jest uszkodzone.
    echo Zmien nazwe katalogu backend\.venv na kopie zapasowa i uruchom skrypt ponownie.
    goto :error
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
