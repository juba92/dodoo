#!/bin/bash
set -e

echo "[dodoo] Installing modules..."
python -m dodoo module install base
python -m dodoo module install account
python -m dodoo module install web
python -m dodoo module install localization
python -m dodoo module install hr
python -m dodoo module install fleet
echo "[dodoo] Modules ready."

echo "[dodoo] Starting server on 0.0.0.0:8080..."
exec python -m dodoo server --host 0.0.0.0 --port 8080
