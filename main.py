from __future__ import annotations

import argparse
import shutil
import subprocess
import threading
import time
import webbrowser

from resq_core.app import create_server
from resq_core.logger import get_logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ResQ local web application")
    parser.add_argument("--host", default=None, help="Host di ascolto")
    parser.add_argument("--port", type=int, default=None, help="Porta di ascolto")
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Apre il browser predefinito dopo l'avvio",
    )
    parser.add_argument(
        "--kiosk",
        action="store_true",
        help="Prova ad aprire Chromium in modalita' kiosk",
    )
    return parser.parse_args()


def launch_browser(url: str, kiosk: bool) -> None:
    logger = get_logger("main")
    time.sleep(1.2)

    if kiosk:
        browser = (
            shutil.which("chromium-browser")
            or shutil.which("chromium")
            or shutil.which("google-chrome")
            or shutil.which("google-chrome-stable")
        )
        if browser:
            command = [
                browser,
                "--kiosk",
                "--noerrdialogs",
                "--disable-infobars",
                "--disable-session-crashed-bubble",
                url,
            ]
            logger.info("Apro Chromium kiosk: %s", " ".join(command))
            subprocess.Popen(command)  # noqa: S603 - command is built from fixed arguments.
            return

        logger.warning("Chromium non trovato, apro il browser predefinito")

    webbrowser.open(url)


def main() -> None:
    args = parse_args()
    server = create_server(host=args.host, port=args.port)
    logger = get_logger("main")

    host, port = server.server_address[:2]
    browser_host = "127.0.0.1" if host in ("", "0.0.0.0") else host
    url = f"http://{browser_host}:{port}"

    if args.open_browser or args.kiosk:
        thread = threading.Thread(
            target=launch_browser,
            args=(url, args.kiosk),
            daemon=True,
        )
        thread.start()

    logger.info("ResQ in ascolto su %s", url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Arresto richiesto da tastiera")
    finally:
        server.server_close()
        logger.info("ResQ arrestato")


if __name__ == "__main__":
    main()

