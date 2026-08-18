from __future__ import annotations

import hashlib
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
from resq_core.clinical_state_machine import ClinicalStateMachine
from resq_core.emergency_flow import EmergencyFlow, FlowError, initial_runtime_state
from resq_core.logger import configure_logging, get_logger
from resq_core.services.app_sync import AppSyncService
from resq_core.services.bom import BOMCatalog
from resq_core.services.call112 import Call112Service
from resq_core.services.emergency_brief import EmergencyBriefContext
from resq_core.services.inventory import InventoryService
from resq_core.services.materials import MaterialService
from resq_core.services.ui_audio import UIAudioService
from resq_core.spec_loader import HandoffSpec, HandoffSpecLoader
from resq_core.state_manager import StateManager
from resq_core.ux_spec_loader import UXSpecLoader


RELEASE_METADATA_FILENAME = "release.json"
RELEASE_SOURCE_ORDER = ("clinical_flow", "state_machine", "automotive_bom")
PRESENTATION_SOURCE_ORDER = (
    "ux_spec",
    "ui_tokens",
    "call112_ux",
    "cpr_metronome_ux",
)


class ReleaseMetadataError(ValueError):
    """Raised when release metadata or its frozen source files are invalid."""


def load_release_metadata(root_dir: Path) -> dict[str, Any]:
    path = root_dir / "config" / RELEASE_METADATA_FILENAME
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseMetadataError(f"Metadata release non leggibili: {path}") from exc
    required = {
        "product",
        "release",
        "candidate_tag",
        "clinical_flow",
        "state_machine",
        "automotive_bom",
        "ux_human_factors",
        "artifact_name",
        "source_of_truth",
        "presentation_sources",
    }
    if not isinstance(metadata, dict) or not required.issubset(metadata):
        raise ReleaseMetadataError("Metadata release incompleti")
    sources = metadata["source_of_truth"]
    if not isinstance(sources, dict) or set(sources) != set(RELEASE_SOURCE_ORDER):
        raise ReleaseMetadataError("Source-of-truth release non validi")
    for source_name in RELEASE_SOURCE_ORDER:
        source = sources[source_name]
        if not isinstance(source, dict) or not {
            "filename",
            "sha256",
        }.issubset(source):
            raise ReleaseMetadataError(
                f"Metadata source-of-truth incompleti: {source_name}"
            )
    presentation_sources = metadata["presentation_sources"]
    if not isinstance(presentation_sources, dict) or set(presentation_sources) != set(
        PRESENTATION_SOURCE_ORDER
    ):
        raise ReleaseMetadataError("Source presentazionali release non validi")
    for source_name in PRESENTATION_SOURCE_ORDER:
        source = presentation_sources[source_name]
        if not isinstance(source, dict) or not {"filename", "sha256"}.issubset(source):
            raise ReleaseMetadataError(
                f"Metadata source presentazionale incompleto: {source_name}"
            )
    return metadata


def runtime_source_filenames(metadata: dict[str, Any]) -> tuple[str, str, str]:
    return tuple(
        str(metadata["source_of_truth"][source_name]["filename"])
        for source_name in RELEASE_SOURCE_ORDER
    )  # type: ignore[return-value]


def presentation_source_filenames(
    metadata: dict[str, Any],
) -> tuple[str, str, str, str]:
    return tuple(
        str(metadata["presentation_sources"][source_name]["filename"])
        for source_name in PRESENTATION_SOURCE_ORDER
    )  # type: ignore[return-value]


def verify_release_sources(root_dir: Path, metadata: dict[str, Any]) -> None:
    spec_dir = root_dir / "config" / "handoff"
    source_groups = (
        (metadata["source_of_truth"], RELEASE_SOURCE_ORDER),
        (metadata["presentation_sources"], PRESENTATION_SOURCE_ORDER),
    )
    for sources, source_order in source_groups:
        for source_name in source_order:
            source = sources[source_name]
            path = spec_dir / str(source["filename"])
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                raise ReleaseMetadataError(
                    f"Source-of-truth non leggibile: {path}"
                ) from exc
            if digest != str(source["sha256"]):
                raise ReleaseMetadataError(
                    f"Hash source-of-truth non valido: {source['filename']}"
                )


RELEASE_METADATA = load_release_metadata(Path(__file__).resolve().parents[1])
RUNTIME_SOURCE_FILENAMES = runtime_source_filenames(RELEASE_METADATA)


def deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(root_dir: Path) -> dict[str, Any]:
    release_metadata = load_release_metadata(root_dir)
    defaults: dict[str, Any] = {
        "app": {
            "name": "ResQ",
            "subtitle": "Smart First Aid Case",
            "host": "127.0.0.1",
            "port": 8080,
            "kiosk": True,
        },
        "logging": {"file": "logs/resq.log"},
        "persistence": {
            "state_file": "data/session_state.json",
            "event_log_file": "data/session_events.jsonl",
        },
        "display": {
            "native_width": 1280,
            "native_height": 720,
            "kiosk_width": 1280,
            "kiosk_height": 720,
            "content_width": 720,
            "content_height": 1280,
            "orientation": "portrait",
            "rotation_degrees": 90,
        },
        "hardware": {"mode": "simulated"},
        "release": release_metadata,
    }
    settings_path = root_dir / "config" / "settings.json"
    if not settings_path.exists():
        return defaults
    with settings_path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    settings = deep_merge(defaults, loaded)
    settings["release"] = release_metadata
    return settings


class ResQHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        root_dir: Path,
        settings: dict[str, Any],
        spec: HandoffSpec,
        flow: EmergencyFlow,
        buttons: ButtonController,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.root_dir = root_dir
        self.settings = settings
        self.spec = spec
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
            if path == "/api/state":
                self._send_json(self.server.flow.public_state())
                return
            if path == "/api/input-feedback":
                self._send_json(self.server.buttons.feedback_snapshot())
                return
            if path == "/api/spec":
                self._send_json(
                    {
                        "version": self.server.spec.version,
                        "bom_version": self.server.spec.bom["bom_version"],
                        "ux_version": self.server.settings["release"][
                            "ux_human_factors"
                        ],
                        "status": self.server.spec.flow["status"],
                        "state_count": len(self.server.spec.states),
                        "sku_count": len(self.server.spec.items),
                        "release": self.server.settings["release"],
                    }
                )
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
            if path == "/api/events":
                event = str(body.get("event", ""))
                if not event:
                    raise FlowError("Evento semantico mancante")
                self._send_json(self.server.flow.dispatch_event(event))
                return
            if path == "/api/session/resume":
                self._send_json(self.server.flow.resume_session())
                return
            if path == "/api/session/discard":
                self._send_json(self.server.flow.discard_session())
                return
            if path == "/api/home":
                self._send_json(self.server.flow.reset_home())
                return
            if path == "/api/audio/repeat":
                self._send_json(self.server.flow.repeat_ux_audio())
                return
            if path == "/api/inventory/correct":
                sku = str(body.get("sku", ""))
                try:
                    quantity = int(body.get("quantity"))
                except (TypeError, ValueError) as exc:
                    raise FlowError("Quantita' inventario non valida") from exc
                if not sku:
                    raise FlowError("SKU inventario mancante")
                self._send_json(self.server.flow.correct_inventory(sku, quantity))
                return
            if path == "/api/inventory/instance":
                sku = str(body.get("sku", ""))
                try:
                    quantity_available = int(body.get("quantity_available"))
                except (TypeError, ValueError) as exc:
                    raise FlowError("Quantita' inventario non valida") from exc
                inserted_at = str(body.get("inserted_at", ""))
                status = str(body.get("status", ""))
                if not sku or not inserted_at or not status:
                    raise FlowError("Dati Inventory Instance incompleti")
                self._send_json(
                    self.server.flow.update_inventory_instance(
                        sku,
                        quantity_available=quantity_available,
                        lot=str(body.get("lot", "")),
                        expiry_date=str(body.get("expiry_date", "")) or None,
                        inserted_at=inserted_at,
                        status=status,
                    )
                )
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
                action = self.server.buttons.handle_button(raw_button)
                if action is None:
                    raise FlowError("Input fisico non posizionale")
                current = self.server.flow.public_state()
                self.server.buttons.configure_soft_keys(current.get("soft_keys", []))
                event = self.server.buttons.event_for_lane(action)
                if event is None:
                    raise FlowError(f"Corsia fisica non attiva: {action}")
                if not self.server.buttons.record_press(action, event):
                    self._send_json(current)
                    return
                payload = self.server.flow.dispatch_event(event)
                self._send_json(payload)
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
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise FlowError("Il body JSON deve essere un oggetto")
        return data

    def _send_json(
        self,
        payload: Any,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        if isinstance(payload, dict) and "soft_keys" in payload:
            self.server.buttons.configure_soft_keys(payload["soft_keys"])
            payload = {
                **payload,
                "input_feedback": self.server.buttons.feedback_snapshot(),
            }
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


def create_runtime(root_dir: Path, data_dir: Path | None = None) -> tuple[EmergencyFlow, ButtonController, HandoffSpec]:
    spec_dir = root_dir / "config" / "handoff"
    release_metadata = load_release_metadata(root_dir)
    verify_release_sources(root_dir, release_metadata)
    flow_filename, architecture_filename, bom_filename = runtime_source_filenames(
        release_metadata
    )
    spec = HandoffSpecLoader(
        spec_dir / flow_filename,
        spec_dir / architecture_filename,
        spec_dir / bom_filename,
    ).load()
    ux_filename, tokens_filename, call112_filename, cpr_filename = (
        presentation_source_filenames(release_metadata)
    )
    ux_spec = UXSpecLoader(
        spec_dir / ux_filename,
        spec_dir / tokens_filename,
        spec_dir / call112_filename,
        spec_dir / cpr_filename,
    ).load(spec)

    engine = ClinicalStateMachine(spec)
    leds = LEDController()
    nfc = NFCReader()
    audio = AudioGuide()
    call112 = Call112Service()
    catalog = BOMCatalog(spec.bom)
    inventory = InventoryService(catalog)
    material_service = MaterialService(catalog, leds, inventory.available_quantity)
    ui_audio = UIAudioService(audio)
    app_sync = AppSyncService()
    emergency_brief = EmergencyBriefContext()
    buttons = ButtonController()

    settings = load_settings(root_dir)
    persistence = settings["persistence"]
    runtime_dir = data_dir if data_dir is not None else root_dir
    state_path = runtime_dir / persistence["state_file"]
    event_log_path = runtime_dir / persistence["event_log_file"]
    initial_state = initial_runtime_state(
        spec,
        engine,
        call112,
        material_service,
        inventory,
        ui_audio,
        app_sync,
        emergency_brief,
    )
    state = StateManager(initial_state, state_path, event_log_path)
    flow = EmergencyFlow(
        spec,
        engine,
        state,
        call112,
        material_service,
        inventory,
        ui_audio,
        app_sync,
        nfc,
        ux_spec,
        emergency_brief,
    )
    return flow, buttons, spec


def create_server(host: str | None = None, port: int | None = None) -> ResQHTTPServer:
    root_dir = Path(__file__).resolve().parents[1]
    settings = load_settings(root_dir)
    log_file = root_dir / settings["logging"]["file"]
    configure_logging(log_file)
    logger = get_logger("app")

    flow, buttons, spec = create_runtime(root_dir)
    DisplayManager().prepare_fullscreen()
    logger.info("Avvio app ResQ con specifica %s", spec.version)

    app_host = host if host is not None else settings["app"]["host"]
    app_port = port if port is not None else int(settings["app"]["port"])

    return ResQHTTPServer(
        (app_host, app_port),
        ResQRequestHandler,
        root_dir=root_dir,
        settings=settings,
        spec=spec,
        flow=flow,
        buttons=buttons,
    )
