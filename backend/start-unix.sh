#!/bin/sh
set -eu

cd "$(dirname "$0")"

echo "=== PECUNIANONOLET BACKEND ==="

PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] <= (3, 13)))' >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo "Wymagany jest Python 3.11, 3.12 lub 3.13."
    exit 1
fi

if [ ! -f ".venv/bin/python" ]; then
    echo "Tworzenie środowiska Python..."
    "$PYTHON_BIN" -m venv .venv
fi

if ! ".venv/bin/python" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] <= (3, 13)))' >/dev/null 2>&1; then
    echo "Istniejace .venv uzywa niewspieranego Pythona lub jest uszkodzone."
    echo "Zmien nazwe katalogu backend/.venv na kopie zapasowa i uruchom skrypt ponownie."
    exit 1
fi

echo "Instalacja zależności skryptu..."
".venv/bin/python" -m pip install -r requirements-runtime.lock.txt

exec ".venv/bin/python" launcher.py "$@"
