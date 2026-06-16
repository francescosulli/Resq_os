#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/resq}"
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$(whoami)}}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "== ResQ install =="
echo "Directory applicazione: ${APP_DIR}"
echo "Utente servizio: ${SERVICE_USER}"

echo "== Pacchetti apt essenziali =="
apt-get update
apt-get install -y python3 python3-venv python3-pip git rsync

if apt-get install -y chromium-browser; then
  echo "Chromium installato: chromium-browser"
elif apt-get install -y chromium; then
  echo "Chromium installato: chromium"
else
  echo "Chromium non installato automaticamente. Il backend funzionera', ma il kiosk richiede un browser."
fi

echo "== Copia file in ${APP_DIR} =="
mkdir -p "${APP_DIR}"
rsync -a --delete \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "logs/*.log" \
  "${SOURCE_DIR}/" "${APP_DIR}/"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"

echo "== Virtual environment =="
sudo -u "${SERVICE_USER}" python3 -m venv "${APP_DIR}/.venv"
sudo -u "${SERVICE_USER}" "${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip
sudo -u "${SERVICE_USER}" "${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

echo "== Systemd =="
SERVICE_TMP="$(mktemp)"
sed "s/^User=.*/User=${SERVICE_USER}/" "${APP_DIR}/system/resq.service" > "${SERVICE_TMP}"
cp "${SERVICE_TMP}" /etc/systemd/system/resq.service
rm -f "${SERVICE_TMP}"

systemctl daemon-reload
systemctl enable resq.service

echo
echo "Installazione completata."
echo "Avvio:       sudo systemctl start resq.service"
echo "Stop:        sudo systemctl stop resq.service"
echo "Stato:       sudo systemctl status resq.service"
echo "Log live:    journalctl -u resq.service -f"
echo "Log app:     ${APP_DIR}/logs/resq.log"

