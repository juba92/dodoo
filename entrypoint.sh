#!/bin/bash
set -e

echo "[dodoo] Installing modules..."
# One process for the whole batch (see dodoo/__main__.py) instead of one process
# per module — each process used to pay its own DB-connect + schema-bootstrap
# cost, which was most of the time this step took.
python -m dodoo module install base account web localization hr fleet product stock stock_account
echo "[dodoo] Modules ready."

echo "[dodoo] Starting server on 0.0.0.0:8080..."
exec python -m dodoo server --host 0.0.0.0 --port 8080
