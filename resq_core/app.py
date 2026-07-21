from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from hardware.audio import AudioGuide
from hardware.buttons import ButtonController
from hardware.display import DisplayManager
from hardware.leds import LEDController
from hardware.nfc import NFCReader
from resq_core.emergency_flow import EmergencyFlow, FlowError
from resq_core.logger import configure_logging, get_logger
from resq_core.protocol_loader import ProtocolLoader
from resq_core.state_manager import StateManager


def deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(root_dir: Path) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "app": {
            "name": "ResQ",
            "subtitle": "Smart First Aid Case",
            "host": "0.0.0.0",
            "port": 8080,
            "kiosk": True,
        },
        "logging": {"file": "logs/resq.log"},
        "display": {
            "native_width": 1280,
            "native_height": 720,
            "kiosk_width": 720,
            "kiosk_height": 1280,
            "orientation": "portrait",
        },
        "hardware": {"mode": "simulated"},
    }
    settings_path = root_dir / "config" / "settings.json"
    if not settings_path.exists():
        return defaults
    with settings_path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    return deep_merge(defaults, loaded)


class ResQHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        root_dir: Path,
        settings: dict[str, Any],
        protocols: dict[str, dict[str, Any]],
        loader: ProtocolLoader,
        flow: EmergencyFlow,
        buttons: ButtonController,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.root_dir = root_dir
        self.settings = settings
        self.protocols = protocols
        self.loader = loader
        self.flow = flow
        self.buttons = buttons
        self.static_dir = root_dir / "static"
        self.templates_dir = root_dir / "templates"


class ResQRequestHandler(BaseHTTPRequestHandler):
    server: ResQHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        get_logger("http").info("%s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path in {"/", "/index.html"}:
                self._serve_file(self.server.templates_dir / "index.html")
                return
            if path.startswith("/static/"):
                relative = unquote(path.removeprefix("/static/"))
                target = self._safe_child(self.server.static_dir, relative)
                self._serve_file(target)
                return
            if path == "/api/protocols":
                self._send_json(self.server.loader.list_summaries(self.server.protocols))
                return
            if path == "/api/state":
                self._send_json(self.server.flow.public_state())
                return
            self._send_json({"error": "Risorsa non trovata"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 - HTTP boundary returns JSON errors.
            self._handle_exception(exc)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            body = self._read_json()

            if path == "/api/emergency/start":
                self._send_json(self.server.flow.start_emergency())
                return
            if path == "/api/home":
                self._send_json(self.server.flow.reset_home())
                return
            if path.startswith("/api/protocols/") and path.endswith("/start"):
                parts = path.split("/")
                protocol_id = unquote(parts[3])
                self._send_json(self.server.flow.start_protocol(protocol_id))
                return
            if path == "/api/answer":
                self._send_json(self.server.flow.answer(str(body.get("answer", ""))))
                return
            if path == "/api/next":
                self._send_json(self.server.flow.next_step())
                return
            if path == "/api/back":
                self._send_json(self.server.flow.back())
                return
            if path == "/api/audio/repeat":
                self._send_json(self.server.flow.repeat_audio())
                return
            if path == "/api/refill/nfc/simulate":
                self._send_json(self.server.flow.simulate_refill_nfc())
                return
            if path.startswith("/api/diagnostics/"):
                test_name = unquote(path.split("/")[-1])
                self._send_json(self.server.flow.run_diagnostic(test_name))
                return
            if path.startswith("/api/buttons/"):
                raw_button = unquote(path.split("/")[-1])
                button = self.server.buttons.handle_button(raw_button)
                self._send_json(self.server.flow.handle_button(button))
                return

            self._send_json({"error": "Risorsa non trovata"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 - HTTP boundary returns JSON errors.
            self._handle_exception(exc)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw:
            return {}
        return json.loads(raw)

    def _send_json(
        self,
        payload: Any,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "File non trovato"}, HTTPStatus.NOT_FOUND)
            return

        content = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".js":
            content_type = "application/javascript"
        if path.suffix == ".css":
            content_type = "text/css"
        if path.suffix == ".html":
            content_type = "text/html"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _safe_child(self, base: Path, relative: str) -> Path:
        target = (base / relative).resolve()
        base_resolved = base.resolve()
        if target == base_resolved or base_resolved in target.parents:
            return target
        raise FlowError("Percorso statico non valido")

    def _handle_exception(self, exc: Exception) -> None:
        logger = get_logger("http")
        if isinstance(exc, FlowError):
            logger.warning("Richiesta non valida: %s", exc)
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        logger.exception("Errore HTTP")
        self._send_json({"error": "Errore interno ResQ"}, HTTPStatus.INTERNAL_SERVER_ERROR)


def create_server(host: str | None = None, port: int | None = None) -> ResQHTTPServer:
    root_dir = Path(__file__).resolve().parents[1]
    settings = load_settings(root_dir)
    log_file = root_dir / settings["logging"]["file"]
    configure_logging(log_file)
    logger = get_logger("app")

    loader = ProtocolLoader(root_dir / "protocols")
    protocols = loader.load_all()
    state = StateManager()
    leds = LEDController()
    nfc = NFCReader()
    audio = AudioGuide()
    display = DisplayManager()
    buttons = ButtonController()
    flow = EmergencyFlow(protocols, state, leds, nfc, audio)

    display.prepare_fullscreen()
    logger.info("Avvio app ResQ")

    app_host = host if host is not None else settings["app"]["host"]
    app_port = port if port is not None else int(settings["app"]["port"])

    return ResQHTTPServer(
        (app_host, app_port),
        ResQRequestHandler,
        root_dir=root_dir,
        settings=settings,
        protocols=protocols,
        loader=loader,
        flow=flow,
        buttons=buttons,
    )
