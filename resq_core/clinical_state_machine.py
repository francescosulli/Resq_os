from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from resq_core.events import EV_AED_AVAILABLE, EV_START_EMERGENCY, soft_keys_for
from resq_core.spec_loader import HandoffSpec


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ClinicalStateError(ValueError):
    """Raised when an event is not valid for the current clinical state."""


@dataclass(frozen=True)
class TransitionResult:
    previous_state: str
    state_id: str
    event: str
    transitioned: bool
    button_label: str | None = None


class ClinicalStateMachine:
    """Pure deterministic transition engine backed by the handoff JSON."""

    def __init__(self, spec: HandoffSpec) -> None:
        self.spec = spec
        self.state_id = "IDLE"
        self.context = self.initial_context()

    def initial_context(self) -> dict[str, Any]:
        return {
            "session_id": None,
            "current_patient": 1,
            "patient_count": None,
            "age_class": "UNKNOWN",
            "call112_status": "IDLE",
            "operator_priority": False,
            "materials_probably_used": [],
            "active_material_request": None,
            "active_led_zone": None,
            "metronome_active": False,
            "aed_present": False,
            "aed_return_state": None,
            "last_transition_at": None,
            "country_profile": "IT_prototype_v1_0",
            "kit_profile": "ResQ_Automotive_BOM_v1_0",
        }

    def restore(self, state_id: str, context: dict[str, Any]) -> None:
        if state_id != "IDLE" and state_id not in self.spec.states:
            raise ClinicalStateError(f"Stato persistito sconosciuto: {state_id}")
        restored = self.initial_context()
        restored.update(copy.deepcopy(context))
        valid_aed_returns = self._valid_aed_return_states()
        if restored.get("aed_return_state") not in valid_aed_returns:
            restored["aed_return_state"] = None
        if state_id == "AED_USE":
            restored["aed_present"] = True
            restored["aed_return_state"] = (
                restored.get("aed_return_state") or self._default_aed_return_state()
            )
        self.state_id = state_id
        self.context = restored

    def reset(self) -> None:
        self.state_id = "IDLE"
        self.context = self.initial_context()

    def dispatch(self, event: str) -> TransitionResult:
        previous = self.state_id
        if previous == "IDLE":
            if event != EV_START_EMERGENCY:
                raise ClinicalStateError(f"Evento {event} non valido in IDLE")
            self._transition_to("EM_START")
            return TransitionResult(previous, self.state_id, event, True, "INIZIA")

        node = self.spec.states[previous]
        parallel_events = node.get("parallel_events", {})
        if event in parallel_events:
            if event == EV_AED_AVAILABLE and self.context.get("aed_present"):
                raise ClinicalStateError("Il DAE e' gia' presente")
            if event == EV_AED_AVAILABLE:
                self.context["aed_return_state"] = self._aed_return_for_source(
                    previous
                )
            self._update_context_from_event(event)
            target = str(parallel_events[event])
            self._transition_to(target)
            return TransitionResult(previous, self.state_id, event, True)

        matching = [
            key
            for key in soft_keys_for(previous, node)
            if key["enabled"] and key["event"] == event
        ]
        if not matching:
            raise ClinicalStateError(f"Evento {event} non valido in {previous}")

        transitions = node.get("next", {})
        targets = {
            transitions[key["label"]]
            for key in matching
            if key["label"] in transitions
        }
        if len(targets) > 1:
            raise ClinicalStateError(
                f"Evento {event} ambiguo in {previous}: target multipli"
            )

        self._update_context_from_event(event)
        if not targets:
            return TransitionResult(previous, previous, event, False, matching[0]["label"])

        target = targets.pop()
        if previous == "AED_USE" and matching[0]["label"] == "FATTO":
            target = self._current_aed_return_state()
        if target == "AED_USE":
            self.context["aed_present"] = True
            self.context["aed_return_state"] = (
                self.context.get("aed_return_state")
                or self._default_aed_return_state()
            )
        self._transition_to(target)
        return TransitionResult(previous, self.state_id, event, True, matching[0]["label"])

    def dispatch_button_label(self, button_label: str, event: str) -> TransitionResult:
        """Dispatch a service-resolved button while keeping its JSON target authoritative."""
        if self.state_id == "IDLE":
            raise ClinicalStateError("Nessun pulsante clinico disponibile in IDLE")
        node = self.spec.states[self.state_id]
        if button_label not in node["buttons"]:
            raise ClinicalStateError(
                f"Pulsante {button_label} non valido in {self.state_id}"
            )
        target = node.get("next", {}).get(button_label)
        if not target:
            raise ClinicalStateError(
                f"Pulsante {button_label} senza transizione in {self.state_id}"
            )
        previous = self.state_id
        self._update_context_from_event(event)
        self._transition_to(target)
        return TransitionResult(previous, self.state_id, event, True, button_label)

    def current_node(self) -> dict[str, Any] | None:
        if self.state_id == "IDLE":
            return None
        return copy.deepcopy(self.spec.states[self.state_id])

    def soft_keys(self) -> list[dict[str, Any]]:
        node = self.current_node()
        if node is None:
            return []
        return soft_keys_for(self.state_id, node)

    def top_level_state(self) -> str:
        if self.state_id == "IDLE":
            return "IDLE"
        if self.state_id in {"POST_EVENT_INVENTORY", "SESSION_END"}:
            return "POST_EVENT"
        return "EMERGENCY"

    def clinical_phase(self) -> str | None:
        state_id = self.state_id
        if state_id == "IDLE" or self.top_level_state() == "POST_EVENT":
            return None
        if state_id.startswith(("SCENE_", "WAIT_SAFE")) or state_id == "EM_START":
            return "SCENE_SAFETY"
        if state_id.startswith("MULTI_"):
            return "MULTI_CASUALTY"
        if state_id.startswith(("MASSIVE_", "BLEED_", "MAT_FALLBACK")) or state_id in {
            "TOURNIQUET",
            "HEMOSTATIC",
            "RESPONSIVE",
        }:
            return "LIFE_THREATS"
        if state_id.startswith(("UNRESP_", "ADULT_", "PED_", "AED_")) or state_id in {
            "AGE_BLS",
            "TRAUMA_UNRESP",
            "RECOVERY_POSITION",
            "TRAUMA_AIRWAY",
        }:
            return "UNRESPONSIVE_BLS"
        if state_id == "MONITOR":
            return "MONITORING"
        if state_id == "HANDOVER":
            return "HANDOVER"
        return "RESPONSIVE_ABCDE"

    def snapshot(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "top_level_state": self.top_level_state(),
            "clinical_phase": self.clinical_phase(),
            "context": copy.deepcopy(self.context),
        }

    def _transition_to(self, target: str) -> None:
        if target != "IDLE" and target not in self.spec.states:
            raise ClinicalStateError(f"Target clinico sconosciuto: {target}")
        self.state_id = target
        self.context["last_transition_at"] = utc_now()
        node = self.current_node()
        self.context["metronome_active"] = bool(node and node.get("metronome"))

    def _update_context_from_event(self, event: str) -> None:
        if event == EV_AED_AVAILABLE:
            self.context["aed_present"] = True
        age_by_event = {
            "EV_SELECT_INFANT": "INFANT",
            "EV_SELECT_CHILD": "CHILD",
            "EV_SELECT_ADULT": "ADULT",
        }
        if event in age_by_event:
            self.context["age_class"] = age_by_event[event]

    def _aed_contract(self) -> dict[str, Any]:
        return self.spec.architecture.get("event_contracts", {}).get(
            EV_AED_AVAILABLE,
            {},
        )

    def _valid_aed_return_states(self) -> set[str]:
        return {
            str(target)
            for target in self._aed_contract().get(
                "return_state_by_source",
                {},
            ).values()
        }

    def _default_aed_return_state(self) -> str:
        target = str(
            self._aed_contract().get("default_return_state", "ADULT_CPR_LOOP")
        )
        if target not in self.spec.states:
            raise ClinicalStateError(f"Ritorno DAE predefinito sconosciuto: {target}")
        return target

    def _aed_return_for_source(self, source_state: str) -> str:
        target = self._aed_contract().get("return_state_by_source", {}).get(
            source_state
        )
        if target is None or str(target) not in self.spec.states:
            raise ClinicalStateError(
                f"Ritorno DAE non definito per lo stato {source_state}"
            )
        return str(target)

    def _current_aed_return_state(self) -> str:
        target = self.context.get("aed_return_state")
        if target not in self._valid_aed_return_states():
            return self._default_aed_return_state()
        return str(target)
