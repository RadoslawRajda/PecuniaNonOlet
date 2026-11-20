#!/bin/sh
set -eu

cd "$(dirname "$0")"

echo "=== PECUNIANONOLET BACKEND ==="

PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo "Wymagany jest Python 3.11 lub nowszy."
    exit 1
fi

if [ ! -f ".venv/bin/python" ]; then
    echo "Tworzenie środowiska Python..."
    "$PYTHON_BIN" -m venv .venv
fi

echo "Instalacja zależności skryptu..."
".venv/bin/python" -m pip install -r requirements-runtime.lock.txt

exec ".venv/bin/python" launcher.py "$@"
