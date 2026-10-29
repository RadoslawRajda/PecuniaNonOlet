#!/bin/sh
set -eu

cd "$(dirname "$0")"

echo "=== PECUNIANONOLET BACKEND ==="

if [ ! -f ".venv/bin/python" ]; then
    echo "Tworzenie środowiska Python..."
    python3 -m venv .venv
fi

echo "Instalacja zależności skryptu..."
".venv/bin/python" -m pip install -r requirements.txt

exec ".venv/bin/python" launcher.py "$@"
