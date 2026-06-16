#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

echo "== ResQ update =="
cd "${APP_DIR}"

echo "== Git pull =="
git pull --ff-only

echo "== Aggiornamento dipendenze =="
if [[ -x "${APP_DIR}/.venv/bin/python" ]]; then
  "${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"
else
  echo "Virtualenv non trovato in ${APP_DIR}/.venv. Esegui install.sh."
fi

echo "== Riavvio servizio =="
systemctl restart resq.service
systemctl status resq.service --no-pager

echo "Aggiornamento completato."

