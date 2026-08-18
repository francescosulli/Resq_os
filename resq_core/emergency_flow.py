from __future__ import annotations

import copy
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from hardware.nfc import NFCReader
from resq_core.clinical_state_machine import ClinicalStateError, ClinicalStateMachine
from resq_core.events import (
    EV_AED_AVAILABLE,
    EV_CALL112_STARTED,
    EV_CLOSE_SESSION,
    EV_DISCARD_SESSION,
    EV_ITEM_TAKEN,
    EV_MATERIAL_NOT_FOUND,
    EV_MATERIAL_TAKEN,
    EV_MATERIAL_UNAVAILABLE,
    EV_OPERATOR_ACTIVE,
    EV_OPERATOR_ENDED,
    EV_PROBLEM,
    EV_REPEAT,
    EV_RESUME_SESSION,
    EV_SKIP,
    EV_START_EMERGENCY,
)
from resq_core.logger import get_logger
from resq_core.services.app_sync import AppSyncService
from resq_core.services.call112 import Call112Service
from resq_core.services.emergency_brief import EmergencyBriefContext
from resq_core.services.inventory import InventoryService
from resq_core.services.materials import MaterialService
from resq_core.services.ui_audio import UIAudioService
from resq_core.spec_loader import HandoffSpec
from resq_core.state_manager import StateManager
from resq_core.ux_spec_loader import UXSpec


RUNTIME_SCHEMA_VERSION = 3
LEGACY_SPEC_VERSION = "v0_5"
COMPATIBLE_SPEC_VERSIONS = {"1.0", "1.1"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FlowError(ValueError):
    """Raised when an application event is not valid in the current state."""


def initial_runtime_state(
    spec: HandoffSpec,
    engine: ClinicalStateMachine,
    call112: Call112Service,
    materials: MaterialService,
    inventory: InventoryService,
    ui_audio: UIAudioService,
    app_sync: AppSyncService,
    emergency_brief: EmergencyBriefContext,
) -> dict[str, Any]:
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "spec_version": spec.version,
        "bom_version": str(spec.bom["bom_version"]),
        **engine.snapshot(),
        "services": {
            "call112": call112.snapshot(),
            "materials": materials.snapshot(),
            "inventory": inventory.snapshot(),
            "ui_audio": ui_audio.snapshot(),
            "app_sync": app_sync.snapshot(),
            "emergency_brief": emergency_brief.snapshot(),
        },
        "session": {
            "active": False,
            "started_at": None,
            "closed_at": None,
        },
        "last_event": None,
    }


class EmergencyFlow:
    """Coordinates the pure clinical engine and event-driven services."""

    def __init__(
        self,
        spec: HandoffSpec,
        engine: ClinicalStateMachine,
        state: StateManager,
        call112: Call112Service,
        materials: MaterialService,
        inventory: InventoryService,
        ui_audio: UIAudioService,
        app_sync: AppSyncService,
        nfc: NFCReader,
        ux_spec: UXSpec,
        emergency_brief: EmergencyBriefContext,
    ) -> None:
        self.spec = spec
        self.engine = engine
        self.state = state
        self.call112 = call112
        self.materials = materials
        self.inventory = inventory
        self.ui_audio = ui_audio
        self.app_sync = app_sync
        self.nfc = nfc
        self.ux_spec = ux_spec
        self.emergency_brief = emergency_brief
        self.logger = get_logger("flow")
        self._lock = RLock()
        self.session = {"active": False, "started_at": None, "closed_at": None}
        self.last_event: str | None = None
        self.resume_required = False
        self.resume_blocked_reason: str | None = None
        self._restore_or_initialize()

    def start_emergency(self) -> dict[str, Any]:
        with self._lock:
            if self.resume_required:
                raise FlowError("E' presente un intervento da riprendere o annullare")
            if self.engine.state_id != "IDLE":
                raise FlowError("Un intervento e' gia' attivo")
            self.session = {
                "active": True,
                "started_at": utc_now(),
                "closed_at": None,
            }
            self.emergency_brief.reset()
            self.engine.context["session_id"] = str(uuid4())
            return self._dispatch(EV_START_EMERGENCY)

    def dispatch_event(self, event: str) -> dict[str, Any]:
        with self._lock:
            if event == EV_RESUME_SESSION:
                return self.resume_session()
            if event == EV_DISCARD_SESSION:
                return self.discard_session()
            if self.resume_required:
                raise FlowError("Prima scegli se riprendere l'intervento")
            return self._dispatch(event)

    def handle_soft_key(self, position: str) -> dict[str, Any]:
        if self.resume_required:
            event_by_position = {"left": EV_DISCARD_SESSION}
            if self.resume_blocked_reason is None:
                event_by_position["right"] = EV_RESUME_SESSION
            event = event_by_position.get(position)
        else:
            event = next(
                (
                    key["event"]
                    for key in self._soft_keys()
                    if key["position"] == position and key["enabled"]
                ),
                None,
            )
        if not event:
            raise FlowError(f"Soft-key {position} non attiva")
        return self.dispatch_event(event)

    def repeat_audio(self) -> dict[str, Any]:
        return self.dispatch_event(EV_REPEAT)

    def repeat_ux_audio(self) -> dict[str, Any]:
        with self._lock:
            if self.resume_required or self.engine.state_id == "IDLE":
                raise FlowError("RIPETI non disponibile")
            presentation = self.ux_spec.states[self.engine.state_id]
            if presentation.get("repeat_mode") != "header_touch":
                raise FlowError("RIPETI header non disponibile in questo stato")
            if self.call112.operator_active:
                raise FlowError("RIPETI disabilitato mentre parla l'operatore 112")
            previous = self.engine.state_id
            self.ui_audio.repeat()
            self.last_event = EV_REPEAT
            self._persist(EV_REPEAT, previous, previous)
            return self.public_state()

    def resume_session(self) -> dict[str, Any]:
        with self._lock:
            if not self.resume_required:
                raise FlowError("Nessun intervento da riprendere")
            if self.resume_blocked_reason:
                raise FlowError(self.resume_blocked_reason)
            self.resume_required = False
            self._enter_current_state()
            self.last_event = EV_RESUME_SESSION
            self._persist(EV_RESUME_SESSION, self.engine.state_id, self.engine.state_id)
            return self.public_state()

    def discard_session(self) -> dict[str, Any]:
        with self._lock:
            if not self.resume_required:
                raise FlowError("Nessun intervento da annullare")
            self.resume_required = False
            self.resume_blocked_reason = None
            return self._reset_home(EV_DISCARD_SESSION)

    def reset_home(self) -> dict[str, Any]:
        with self._lock:
            if (
                self.engine.top_level_state() == "EMERGENCY"
                and self.engine.state_id != "EM_START"
            ):
                raise FlowError("La home non puo' interrompere un intervento attivo")
            return self._reset_home(EV_CLOSE_SESSION)

    def correct_inventory(self, sku: str, quantity: int) -> dict[str, Any]:
        with self._lock:
            if self.engine.state_id != "POST_EVENT_INVENTORY":
                raise FlowError("Correzione inventario disponibile solo nel post-evento")
            if not self.inventory.correction_enabled:
                raise FlowError("Premi CORREGGI prima di modificare le quantita'")
            try:
                self.inventory.correct_pending(sku, quantity)
            except (ValueError, KeyError) as exc:
                raise FlowError(str(exc)) from exc
            self._sync_context()
            record = {
                "schema_version": RUNTIME_SCHEMA_VERSION,
                "kind": "service_action",
                "service": "InventoryService",
                "action": "CORRECT_PENDING",
                "sku": sku,
                "quantity": quantity,
                "state": self.engine.state_id,
                "at": utc_now(),
            }
            self.state.save(self._runtime_snapshot(), record)
            return self.public_state()

    def update_inventory_instance(
        self,
        sku: str,
        *,
        quantity_available: int,
        lot: str,
        expiry_date: str | None,
        inserted_at: str,
        status: str,
    ) -> dict[str, Any]:
        with self._lock:
            self._require_idle_maintenance()
            try:
                self.inventory.update_instance(
                    sku,
                    quantity_available=quantity_available,
                    lot=lot,
                    expiry_date=expiry_date,
                    inserted_at=inserted_at,
                    status=status,
                )
            except (ValueError, KeyError) as exc:
                raise FlowError(str(exc)) from exc
            self.inventory.mark_sync_pending()
            self.app_sync.queue_sync(self.inventory.snapshot())
            record = {
                "schema_version": RUNTIME_SCHEMA_VERSION,
                "kind": "service_action",
                "service": "InventoryService",
                "action": "UPDATE_INSTANCE",
                "sku": sku,
                "quantity_available": quantity_available,
                "status": status,
                "at": utc_now(),
            }
            self.state.save(self._runtime_snapshot(), record)
            return self.public_state()

    def simulate_refill_nfc(self) -> dict[str, Any]:
        with self._lock:
            self._require_idle_maintenance()
            item_name = "Refill demo: garze sterili"
            detected_tag = self.nfc.simulate_refill(item_name)
            message = f"[NFC REFILL] Refill registrato: {detected_tag}"
            self.logger.info(message)
            return {
                "test": "refill_nfc",
                "message": message,
                "state": self.public_state(),
            }

    def run_diagnostic(self, test_name: str) -> dict[str, Any]:
        with self._lock:
            self._require_idle_maintenance()
            if test_name == "led":
                message = self.materials.leds.test_sequence()
            elif test_name == "refill_nfc":
                return self.simulate_refill_nfc()
            elif test_name == "audio":
                message = self.ui_audio.audio.test()
            elif test_name == "status":
                message = "App attiva, UX 1.1 e servizi offline pronti"
            else:
                raise FlowError("Test diagnostico non riconosciuto")
            return {
                "test": test_name,
                "message": message,
                "state": self.public_state(),
            }

    def public_state(self) -> dict[str, Any]:
        with self._lock:
            engine_state = self.engine.snapshot()
            node = self.engine.current_node()
            presented_node = self._presented_node(node)
            if self.resume_required:
                mode = "resume"
                can_resume = self.resume_blocked_reason is None
                soft_keys = [
                    {
                        "position": "left",
                        "label": "ANNULLA",
                        "event": EV_DISCARD_SESSION,
                        "enabled": True,
                        "color_role": "neutral",
                        "icon": "exit",
                    },
                ]
                if can_resume:
                    soft_keys.append(
                        {
                            "position": "right",
                            "label": "RIPRENDI",
                            "event": EV_RESUME_SESSION,
                            "enabled": True,
                            "color_role": "success",
                            "icon": "arrow_right",
                        }
                    )
                label = "Intervento in corso"
                prompt = self.resume_blocked_reason or (
                    "ResQ ha trovato un intervento non concluso. Vuoi riprenderlo?"
                )
                state_type = "resume"
            else:
                top_level = engine_state["top_level_state"]
                mode = {
                    "IDLE": "home",
                    "EMERGENCY": "emergency",
                    "POST_EVENT": "post_event",
                }[top_level]
                soft_keys = self._soft_keys()
                label = (
                    presented_node.get("label", "ResQ")
                    if presented_node
                    else "ResQ"
                )
                prompt = presented_node.get("prompt", "") if presented_node else ""
                state_type = (
                    presented_node.get("type", "idle")
                    if presented_node
                    else "idle"
                )

            material_snapshot = self.materials.snapshot()
            call_snapshot = self.call112.snapshot()
            ux_snapshot = self._ux_snapshot()
            return {
                "version": self.spec.version,
                "ux_version": self.ux_spec.version,
                "bom_version": str(self.spec.bom["bom_version"]),
                "clinical_status": self.spec.flow["status"],
                "mode": mode,
                "state_id": engine_state["state_id"],
                "top_level_state": engine_state["top_level_state"],
                "clinical_phase": engine_state["clinical_phase"],
                "label": label,
                "type": state_type,
                "prompt": prompt,
                "soft_keys": soft_keys,
                "ux": ux_snapshot,
                "context": engine_state["context"],
                "session": copy.deepcopy(self.session),
                "resume_required": self.resume_required,
                "resume_blocked_reason": self.resume_blocked_reason,
                "last_event": self.last_event,
                "services": {
                    "call112": call_snapshot,
                    "materials": material_snapshot,
                    "inventory": self.inventory.snapshot(),
                    "ui_audio": self.ui_audio.snapshot(),
                    "app_sync": self.app_sync.snapshot(),
                    "emergency_brief": self.emergency_brief.snapshot(),
                },
                "led_status": {
                    "active": bool(material_snapshot["active_led_zone"]),
                    "zone": material_snapshot["active_led_zone"] or "",
                    "led_id": material_snapshot["active_led_id"] or "",
                    "message": material_snapshot["led_message"],
                },
            }

    def _dispatch(self, event: str) -> dict[str, Any]:
        previous = self.engine.state_id

        if event in {EV_OPERATOR_ACTIVE, EV_OPERATOR_ENDED}:
            if self.engine.top_level_state() != "EMERGENCY":
                raise FlowError("Evento operatore 112 valido solo durante l'emergenza")
            if not self.call112.handle_event(event):
                raise FlowError(f"Evento servizio non gestito: {event}")
            self.ui_audio.set_operator_active(self.call112.operator_active)
            self._sync_context()
            self.last_event = event
            self._persist(event, previous, previous)
            return self.public_state()

        if event == EV_REPEAT and self.call112.operator_active:
            raise FlowError("RIPETI disabilitato mentre parla l'operatore 112")

        if event == EV_MATERIAL_NOT_FOUND:
            return self._handle_material_not_found()

        if event in {EV_MATERIAL_TAKEN, EV_ITEM_TAKEN}:
            active = self.materials.active_request or {}
            if not active.get("resolved"):
                raise FlowError("Nessuno SKU BOM disponibile da confermare")

        try:
            result = self.engine.dispatch(event)
        except ClinicalStateError as exc:
            raise FlowError(str(exc)) from exc

        self.emergency_brief.observe(previous, event, result.state_id)

        if event == EV_CALL112_STARTED:
            self.call112.handle_event(event)
        if event in {EV_MATERIAL_TAKEN, EV_ITEM_TAKEN}:
            self.inventory.mark_pending(self.materials.take_active())
        if event == EV_SKIP:
            self.materials.skip_active()
        if event == EV_REPEAT:
            self.ui_audio.repeat()
        if event == EV_PROBLEM and previous == "POST_EVENT_INVENTORY":
            self.inventory.enable_correction()

        if previous == "EM_START" and event == EV_CLOSE_SESSION and not result.transitioned:
            return self._reset_home(event)

        if result.transitioned:
            response = self._complete_transition(previous, event, result.state_id)
            if response is not None:
                return response

        self._sync_context()
        self.last_event = event
        self._persist(event, previous, self.engine.state_id)
        return self.public_state()

    def _handle_material_not_found(self) -> dict[str, Any]:
        previous = self.engine.state_id
        valid = any(
            key["enabled"] and key["event"] == EV_MATERIAL_NOT_FOUND
            for key in self._soft_keys()
        )
        if not valid:
            raise FlowError(f"Evento {EV_MATERIAL_NOT_FOUND} non valido in {previous}")
        if not self.materials.active_request:
            raise FlowError("Nessuna MaterialRequest attiva")

        active_request = self.materials.active_request
        reported_missing = copy.deepcopy(active_request.get("resolved"))
        if not reported_missing:
            raise FlowError("Nessuno SKU BOM risolto da segnalare come non trovato")
        self.inventory.mark_suspected_missing(reported_missing)
        resolved_fallback = self.materials.report_not_found()
        self._sync_context()
        self.last_event = EV_MATERIAL_NOT_FOUND
        self._persist(
            EV_MATERIAL_NOT_FOUND,
            previous,
            previous,
            record_updates={
                "resolved_sku": reported_missing["sku"],
                "inventory_status": "SUSPECTED_MISSING",
            },
        )
        if resolved_fallback:
            return self.public_state()

        node = self.engine.current_node() or {}
        if node.get("type") == "material_action_optional":
            return self.public_state()

        try:
            result = self.engine.dispatch_button_label(
                "NON TROVO",
                EV_MATERIAL_UNAVAILABLE,
            )
        except ClinicalStateError as exc:
            raise FlowError(str(exc)) from exc

        response = self._complete_transition(
            previous,
            EV_MATERIAL_UNAVAILABLE,
            result.state_id,
        )
        if response is not None:
            return response
        self._sync_context()
        self.last_event = EV_MATERIAL_UNAVAILABLE
        self._persist(EV_MATERIAL_UNAVAILABLE, previous, self.engine.state_id)
        return self.public_state()

    def _complete_transition(
        self,
        previous: str,
        event: str,
        state_id: str,
    ) -> dict[str, Any] | None:
        if state_id == "IDLE":
            return self._reset_home(event, previous_state=previous)
        self._enter_current_state()
        if state_id == "POST_EVENT_INVENTORY":
            self.inventory.begin_review()
        if previous == "POST_EVENT_INVENTORY" and event == EV_CLOSE_SESSION:
            self.inventory.finalize_pending()
            self.inventory.mark_sync_pending()
            self.app_sync.queue_sync(self.inventory.snapshot())
            self.session["active"] = False
            self.session["closed_at"] = utc_now()
        return None

    def _enter_current_state(self) -> None:
        node = self.engine.current_node()
        if node is None:
            return
        self.call112.apply_policy(node.get("call112"))
        self.ui_audio.render(
            self._presented_node(node) or node,
            operator_active=self.call112.operator_active,
        )
        self.materials.enter_state(node)
        self._sync_context()

    def _soft_keys(self) -> list[dict[str, Any]]:
        if self.engine.state_id == "IDLE":
            return []
        controls = self.ux_spec.states[self.engine.state_id]["primary_controls"]
        soft_keys = []
        for position in ("left", "center", "right"):
            control = controls.get(position)
            if not control:
                continue
            if (
                control["semantic_event"] == EV_AED_AVAILABLE
                and self.engine.context.get("aed_present")
            ):
                continue
            if (
                control["semantic_event"] == EV_REPEAT
                and self.call112.operator_active
            ):
                continue
            soft_keys.append(
                {
                    "position": position,
                    "label": str(control["display_label"]),
                    "event": str(control["semantic_event"]),
                    "enabled": bool(
                        control.get("touch_enabled")
                        and control.get("physical_enabled")
                    ),
                    "touch_enabled": bool(control.get("touch_enabled")),
                    "physical_enabled": bool(control.get("physical_enabled")),
                    "color_role": str(control["color_role"]),
                    "icon": str(control.get("icon") or "choice"),
                    "source_button_label": control.get("source_button_label"),
                }
            )
        return soft_keys

    def _ux_snapshot(self) -> dict[str, Any]:
        color_tokens = self.ux_spec.tokens["color_system"]["tokens"]
        if self.engine.state_id == "IDLE":
            return {
                "version": self.ux_spec.version,
                "state_id": None,
                "repeat": {"mode": "none", "enabled": False},
                "call112": {"visible": False, "mode": "hidden"},
                "metronome": {"active": False},
                "color_tokens": copy.deepcopy(color_tokens),
            }

        presentation = self.ux_spec.states[self.engine.state_id]
        repeat_mode = str(presentation["repeat_mode"])
        repeat_enabled = repeat_mode != "none" and not self.call112.operator_active
        cpr_active = presentation.get("cpr_metronome") != "off"
        metronome = self.ux_spec.cpr["metronome"]
        aed_control = presentation.get("aed_availability_control") or {}
        aed_present = bool(self.engine.context.get("aed_present"))
        aed_event = aed_control.get("semantic_event")
        current_node = self.engine.current_node() or {}
        aed_guidance = self._aed_guidance(current_node)
        aed_primary_lane = next(
            (
                lane
                for lane, control in presentation["primary_controls"].items()
                if control.get("semantic_event") == EV_AED_AVAILABLE
            ),
            None,
        )
        aed_interactive = bool(
            cpr_active
            and aed_event
            and aed_control.get("touch_enabled")
            and aed_primary_lane is None
            and not aed_present
        )
        duck_db = float(
            self.ux_spec.cpr.get("operator_priority", {}).get(
                "default_duck_db",
                -12,
            )
        )
        return {
            "version": self.ux_spec.version,
            "state_id": self.engine.state_id,
            "screen_mode": str(presentation["screen_mode"]),
            "active_primary_count": len(self._soft_keys()),
            "repeat": {
                "mode": repeat_mode,
                "enabled": repeat_enabled,
                "event": EV_REPEAT,
                "placement": "header" if repeat_mode == "header_touch" else "lane",
                "operator_suppressed": self.call112.operator_active,
            },
            "call112": self._call112_ux_snapshot(presentation),
            "metronome": {
                "active": cpr_active,
                "target_bpm": int(metronome["target_bpm"]),
                "beat_interval_ms": float(metronome["beat_interval_ms_nominal"]),
                "range_bpm": list(metronome["guideline_range_bpm"]),
                "label": str(metronome["visual"]["show_label"]),
                "range_label": str(metronome["visual"]["show_target"]),
                "audio_kind": str(metronome["audio"]["sound"]),
                "visual_pulse": bool(metronome["visual"]["synchronized_pulse"]),
                "operator_ducked": cpr_active and self.call112.operator_active,
                "duck_db": duck_db,
                "automatic_30_2": False,
            },
            "aed_reminder": {
                "visible": bool(cpr_active and (aed_primary_lane is None or aed_present)),
                "label": (
                    "DAE PRESENTE"
                    if aed_present
                    else str(
                        aed_control.get("display_label")
                        or "DAE APPENA DISPONIBILE"
                    )
                ),
                "interactive": aed_interactive,
                "present": aed_present,
                "event": str(aed_event) if aed_interactive else None,
                "color_role": str(aed_control.get("color_role") or "neutral"),
                "physical_enabled": bool(aed_control.get("physical_enabled")),
                "physical_lane": aed_control.get("physical_lane"),
                "clinical_gap": aed_control.get("clinical_gap"),
                "clinical_transition_available": bool(
                    aed_event
                    and current_node.get("parallel_events", {}).get(
                        EV_AED_AVAILABLE
                    )
                    == "AED_USE"
                ),
            },
            "aed_use": {
                "active": self.engine.state_id == "AED_USE",
                "title": "USA IL DAE",
                "age_class": str(self.engine.context.get("age_class") or "UNKNOWN"),
                "guidance": aed_guidance,
            },
            "color_tokens": copy.deepcopy(color_tokens),
        }

    def _presented_node(
        self,
        node: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if node is None:
            return None
        presented = copy.deepcopy(node)
        guidance = self._aed_guidance(node)
        if guidance:
            presented["prompt"] = " ".join(
                str(guidance[key]) for key in ("lead", "mode", "fallback")
            )
        elif self.engine.context.get("aed_present"):
            presentation = self.ux_spec.states.get(self.engine.state_id, {})
            post_aed_prompt = presentation.get("prompt_when_aed_present")
            if post_aed_prompt:
                presented["prompt"] = str(post_aed_prompt)
        return presented

    def _aed_guidance(self, node: dict[str, Any]) -> dict[str, str] | None:
        if self.engine.state_id != "AED_USE":
            return None
        guidance_by_age = node.get("aed_guidance_by_age_class", {})
        age_class = str(self.engine.context.get("age_class") or "UNKNOWN")
        guidance = guidance_by_age.get(age_class) or guidance_by_age.get("UNKNOWN")
        if not isinstance(guidance, dict):
            return None
        return {
            key: str(guidance[key])
            for key in ("lead", "mode", "fallback")
        }

    def _call112_ux_snapshot(
        self,
        state_presentation: dict[str, Any],
    ) -> dict[str, Any]:
        service = self.call112.snapshot()
        policies = self.ux_spec.call112["policy_to_presentation"]
        if service["operator_active"]:
            presentation_key = "OPERATOR_PRIORITY"
        elif service.get("call_started"):
            presentation_key = "USER_CALLING"
        elif service.get("policy") == "OPERATOR_PRIORITY":
            presentation_key = "RECOMMENDED_IMMEDIATE"
        elif service.get("policy") in policies:
            presentation_key = str(service["policy"])
        elif service["state"] in policies:
            presentation_key = str(service["state"])
        else:
            presentation_key = None

        if presentation_key is None:
            return {
                "visible": False,
                "mode": "hidden",
                "requested_mode": state_presentation.get("call112_presentation"),
                "operator_active": False,
                "briefing": None,
            }

        configured = copy.deepcopy(policies[presentation_key])
        visible = configured.get("mode") != "no_call_now_banner"
        if service["operator_active"]:
            display_variant = "compact_operator"
        elif self.engine.state_id == "UNRESP_CALL" and not service.get("call_started"):
            display_variant = "call_now"
        else:
            display_variant = "compact"
        if display_variant == "compact_operator":
            compact_label = "SEGUI L'OPERATORE 112"
        elif service.get("call_started"):
            compact_label = "112 IN CORSO"
        else:
            compact_label = str(configured.get("headline") or "CHIAMA IL 112")
        briefing = None
        if visible and display_variant == "call_now":
            values = self.emergency_brief.snapshot()["briefing_compact"]
            brief_spec = self.ux_spec.call112["call_briefing"]
            briefing_items = []
            for item in brief_spec["items"]:
                observed_value = values.get(item["id"])
                briefing_items.append(
                    {
                        "id": str(item["id"]),
                        "label": str(item["label"]),
                        "observed": observed_value is not None,
                        "text": observed_value,
                        "fallback_prompt": str(item["fallback_prompt"]),
                        "display_fallback": str(item["display_fallback"]),
                    }
                )
            briefing = {
                "title": str(brief_spec["title"]),
                "items": briefing_items,
                "footer": str(brief_spec["footer"]),
            }
        return {
            **configured,
            "visible": visible,
            "policy": presentation_key,
            "display_variant": display_variant,
            "compact_label": compact_label,
            "requested_mode": state_presentation.get("call112_presentation"),
            "operator_active": bool(service["operator_active"]),
            "briefing": briefing,
        }

    def _sync_context(self) -> None:
        material_snapshot = self.materials.snapshot()
        call_snapshot = self.call112.snapshot()
        inventory_snapshot = self.inventory.snapshot()
        self.engine.context["call112_status"] = call_snapshot["state"]
        self.engine.context["operator_priority"] = call_snapshot["operator_priority"]
        self.engine.context["materials_probably_used"] = inventory_snapshot[
            "pending_material_requests"
        ]
        active_request = material_snapshot.get("active_request")
        self.engine.context["active_material_request"] = (
            active_request.get("material_id") if active_request else None
        )
        self.engine.context["active_led_zone"] = material_snapshot["active_led_zone"]
        self.engine.context["metronome_active"] = self.ui_audio.metronome_active

    def _reset_home(
        self,
        event: str,
        previous_state: str | None = None,
    ) -> dict[str, Any]:
        previous = previous_state or self.engine.state_id
        session_id = self.engine.context.get("session_id")
        closed_at = self.session.get("closed_at") or utc_now()
        active_request = self.materials.snapshot().get("active_request") or {}
        resolved = active_request.get("resolved") or {}
        final_record = {
            "material_request": active_request.get("material_id"),
            "resolved_sku": resolved.get("sku"),
            "call112_status": self.call112.state,
        }

        self.engine.reset()
        self.call112.reset()
        self.materials.reset()
        self.inventory.discard_pending()
        self.ui_audio.reset()
        self.emergency_brief.reset()
        self.session = {
            "active": False,
            "started_at": None,
            "closed_at": closed_at,
        }
        self.last_event = event
        self._persist(
            event,
            previous,
            "IDLE",
            session_id_override=session_id,
            record_updates=final_record,
        )
        return self.public_state()

    def _restore_or_initialize(self) -> None:
        snapshot = self.state.snapshot()
        if not self.state.loaded_from_disk:
            self._persist(None, "IDLE", "IDLE")
            return

        persisted_version = str(snapshot.get("spec_version", ""))
        if persisted_version == self.spec.version:
            self._restore_v1(snapshot)
            return
        if persisted_version in COMPATIBLE_SPEC_VERSIONS:
            self._restore_v1(snapshot)
            self._persist(None, self.engine.state_id, self.engine.state_id)
            return
        if persisted_version == LEGACY_SPEC_VERSION:
            self._restore_legacy_v05(snapshot)
            return
        raise FlowError(
            f"Versione stato persistito non supportata: {persisted_version or 'assente'}"
        )

    def _restore_v1(self, snapshot: dict[str, Any]) -> None:
        if str(snapshot.get("bom_version")) != str(self.spec.bom["bom_version"]):
            raise FlowError("Lo stato persistito appartiene a una BOM diversa")
        self.engine.restore(snapshot["state_id"], snapshot.get("context", {}))
        services = snapshot.get("services", {})
        self.call112.restore(services.get("call112", {}))
        self.inventory.restore(services.get("inventory", {}))
        self.materials.restore(services.get("materials", {}))
        self.ui_audio.restore(services.get("ui_audio", {}))
        self.app_sync.restore(services.get("app_sync", {}))
        self.emergency_brief.restore(services.get("emergency_brief", {}))
        if self.app_sync.queue_state == "SYNC_PENDING":
            self.app_sync.queue_sync(self.inventory.snapshot())
        self.session = copy.deepcopy(snapshot.get("session", self.session))
        self.last_event = snapshot.get("last_event")
        self.resume_required = (
            self.engine.top_level_state() in {"EMERGENCY", "POST_EVENT"}
            and self.engine.state_id != "SESSION_END"
        )
        if int(snapshot.get("schema_version", 0)) < RUNTIME_SCHEMA_VERSION:
            self._persist(None, self.engine.state_id, self.engine.state_id)

    def _restore_legacy_v05(self, snapshot: dict[str, Any]) -> None:
        services = snapshot.get("services", {})
        self.inventory.restore_legacy(services.get("inventory", {}))
        legacy_sync = services.get("app_sync", {})
        if self.inventory.local_dirty or legacy_sync.get("queue_state") == "SYNC_PENDING":
            self.app_sync.queue_sync(self.inventory.snapshot())

        legacy_state = str(snapshot.get("state_id", "IDLE"))
        self.last_event = snapshot.get("last_event")
        if legacy_state in {"IDLE", "SESSION_END"}:
            self.engine.reset()
            self.call112.reset()
            self.materials.reset()
            self.ui_audio.reset()
            self.emergency_brief.reset()
            self.session = copy.deepcopy(snapshot.get("session", self.session))
            self.session["active"] = False
            self.logger.info("Persistenza v0.5 IDLE migrata allo schema v1.2")
            self._persist(None, legacy_state, "IDLE")
            return

        if legacy_state in self.spec.states:
            self.engine.restore(legacy_state, snapshot.get("context", {}))
        else:
            self.engine.reset()
        self.engine.context["country_profile"] = "IT_prototype_v1_0"
        self.engine.context["kit_profile"] = "ResQ_Automotive_BOM_v1_0"
        self.call112.restore(services.get("call112", {}))
        self.materials.reset()
        self.ui_audio.reset()
        self.emergency_brief.reset()
        self.session = copy.deepcopy(snapshot.get("session", self.session))
        self.resume_required = True
        self.resume_blocked_reason = (
            "L'intervento appartiene al flow v0.5 e non puo' essere convertito "
            "automaticamente. Annullalo per avviare il Flow v1.2."
        )

    def _runtime_snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "spec_version": self.spec.version,
            "bom_version": str(self.spec.bom["bom_version"]),
            **self.engine.snapshot(),
            "services": {
                "call112": self.call112.snapshot(),
                "materials": self.materials.snapshot(),
                "inventory": self.inventory.snapshot(),
                "ui_audio": self.ui_audio.snapshot(),
                "app_sync": self.app_sync.snapshot(),
                "emergency_brief": self.emergency_brief.snapshot(),
            },
            "session": copy.deepcopy(self.session),
            "last_event": self.last_event,
        }

    def _persist(
        self,
        event: str | None,
        previous: str,
        current: str,
        *,
        session_id_override: str | None = None,
        record_updates: dict[str, Any] | None = None,
    ) -> None:
        record = None
        if event:
            active_request = self.materials.snapshot().get("active_request") or {}
            resolved = active_request.get("resolved") or {}
            record = {
                "schema_version": RUNTIME_SCHEMA_VERSION,
                "session_id": (
                    session_id_override
                    if session_id_override is not None
                    else self.engine.context.get("session_id")
                ),
                "event": event,
                "from": previous,
                "to": current,
                "at": utc_now(),
                "material_request": active_request.get("material_id"),
                "resolved_sku": resolved.get("sku"),
                "call112_status": self.call112.state,
            }
            if record_updates:
                record.update(copy.deepcopy(record_updates))
            self.logger.info("Evento %s: %s -> %s", event, previous, current)
        self.state.save(self._runtime_snapshot(), record)

    def _require_idle_maintenance(self) -> None:
        if self.engine.top_level_state() != "IDLE" or self.resume_required:
            raise FlowError("Diagnostica e refill disponibili solo dalla Home")
