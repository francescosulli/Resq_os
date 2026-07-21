#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
APP_USER="${APP_USER:-$(stat -c "%U" "${APP_DIR}" 2>/dev/null || echo "${SUDO_USER:-$(whoami)}")}"

if [[ "${APP_USER}" == "root" && -n "${SUDO_USER:-}" ]]; then
  APP_USER="${SUDO_USER}"
fi

APP_HOME="$(getent passwd "${APP_USER}" 2>/dev/null | cut -d: -f6 || true)"

run_as_app_user() {
  if [[ "$(id -un)" == "${APP_USER}" ]]; then
    "$@"
    return
  fi

  if [[ -n "${APP_HOME}" ]]; then
    sudo -H -u "${APP_USER}" env HOME="${APP_HOME}" "$@"
  else
    sudo -H -u "${APP_USER}" "$@"
  fi
}

run_systemctl() {
  if [[ "${EUID}" -eq 0 ]]; then
    systemctl "$@"
  else
    sudo systemctl "$@"
  fi
}

echo "== ResQ update =="
echo "Directory applicazione: ${APP_DIR}"
echo "Utente git/app: ${APP_USER}"
cd "${APP_DIR}"

echo "== Git pull =="
if ! run_as_app_user git pull --ff-only; then
  echo
  echo "Git pull non riuscito."
  echo "Se leggi 'invalid username or token', GitHub sta rifiutando l'autenticazione."
  echo
  echo "Soluzione consigliata sul Raspberry:"
  echo "  1. Configura una chiave SSH per l'utente ${APP_USER}"
  echo "  2. Aggiungi la chiave pubblica a GitHub"
  echo "  3. Cambia il remote da HTTPS a SSH:"
  echo "     git remote set-url origin git@github.com:francescosulli/Resq_os.git"
  echo
  echo "Remote attuale:"
  run_as_app_user git remote -v || true
  exit 1
fi

echo "== Aggiornamento dipendenze =="
if [[ -x "${APP_DIR}/.venv/bin/python" ]]; then
  run_as_app_user "${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"
else
  echo "Virtualenv non trovato in ${APP_DIR}/.venv. Esegui install.sh."
fi

echo "== Riavvio servizio =="
run_systemctl restart resq.service
run_systemctl status resq.service --no-pager

echo "Aggiornamento completato."
