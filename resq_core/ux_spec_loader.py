from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from resq_core.events import (
    EV_AED_AVAILABLE,
    EV_MATERIAL_NOT_FOUND,
    EV_REPEAT,
    event_for_button,
)
from resq_core.spec_loader import HandoffSpec


class UXSpecError(ValueError):
    """Raised when UX 1.1 contradicts the active clinical contract."""


@dataclass(frozen=True)
class UXSpec:
    ux: dict[str, Any]
    tokens: dict[str, Any]
    call112: dict[str, Any]
    cpr: dict[str, Any]

    @property
    def version(self) -> str:
        return str(self.ux["version"])

    @property
    def states(self) -> dict[str, dict[str, Any]]:
        return self.ux["states"]

    def state(self, state_id: str) -> dict[str, Any]:
        return copy.deepcopy(self.states[state_id])


class UXSpecLoader:
    LANES = ("left", "center", "right")
    SCREEN_MODES = {"EVALUATION", "ACTION", "CRITICAL_ACTION", "CALL_112"}
    ACTION_COLOR_ROLES = {
        "PROBLEMA": "danger",
        "NON TROVO": "danger",
        "PEGGIORA": "danger",
        "NON SO": "warning",
        "RIPETI": "support",
        "FATTO": "success",
        "PRESO": "success",
        "CONTINUA": "success",
        "HO CHIAMATO": "success",
        "STABILE": "success",
        "SALTA": "neutral",
        "ESCI": "neutral",
    }
    SOURCE_FILENAMES = {
        "clinical_flow": "ResQ_flow_nodes_v1_2.json",
        "state_machine": "ResQ_state_machine_spec_v1_2.yaml",
        "automotive_bom": "ResQ_Automotive_BOM_v1_0.yaml",
    }

    def __init__(
        self,
        ux_path: str | Path,
        tokens_path: str | Path,
        call112_path: str | Path,
        cpr_path: str | Path,
    ) -> None:
        self.ux_path = Path(ux_path)
        self.tokens_path = Path(tokens_path)
        self.call112_path = Path(call112_path)
        self.cpr_path = Path(cpr_path)

    def load(self, clinical: HandoffSpec) -> UXSpec:
        sources = [
            self._read_yaml(self.ux_path),
            self._read_yaml(self.tokens_path),
            self._read_yaml(self.call112_path),
            self._read_yaml(self.cpr_path),
        ]
        spec = UXSpec(*sources)
        self._validate(spec, clinical)
        return spec

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        try:
            source = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise UXSpecError(f"Source UX non leggibile: {path}") from exc
        if not isinstance(source, dict):
            raise UXSpecError(f"Source UX senza root a oggetto: {path}")
        return source

    def _validate(self, spec: UXSpec, clinical: HandoffSpec) -> None:
        if any(
            str(source.get("version")) != "1.1"
            for source in (spec.ux, spec.tokens, spec.call112, spec.cpr)
        ):
            raise UXSpecError("Tutti i source UX devono essere in versione 1.1")
        if spec.ux.get("scope") != "presentation_only":
            raise UXSpecError("La UX 1.1 deve avere scope esclusivamente presentazionale")
        if spec.ux.get("inherits") != self.SOURCE_FILENAMES:
            raise UXSpecError("La UX 1.1 non eredita i source di release attivi")
        if set(spec.states) != set(clinical.states):
            missing = set(clinical.states) - set(spec.states)
            extra = set(spec.states) - set(clinical.states)
            raise UXSpecError(
                f"Mapping UX stati non completo; mancanti={sorted(missing)}, extra={sorted(extra)}"
            )

        self._validate_tokens(spec)
        self._validate_call112(spec)
        self._validate_cpr(spec, clinical)
        for state_id, node in clinical.states.items():
            self._validate_state(spec, clinical, state_id, node)

    def _validate_state(
        self,
        spec: UXSpec,
        clinical: HandoffSpec,
        state_id: str,
        node: dict[str, Any],
    ) -> None:
        presentation = spec.states[state_id]
        controls = presentation.get("primary_controls")
        if not isinstance(controls, dict):
            raise UXSpecError(f"{state_id}: primary_controls non validi")
        if set(controls).difference(self.LANES):
            raise UXSpecError(f"{state_id}: lane UX sconosciuta")
        if not 1 <= len(controls) <= 3:
            raise UXSpecError(f"{state_id}: servono da 1 a 3 controlli attivi")
        if int(presentation.get("active_primary_count", 0)) != len(controls):
            raise UXSpecError(f"{state_id}: active_primary_count non coerente")
        screen_mode = presentation.get("screen_mode")
        if screen_mode not in self.SCREEN_MODES:
            raise UXSpecError(f"{state_id}: screen_mode non valido")
        if state_id == "UNRESP_CALL" and screen_mode != "CALL_112":
            raise UXSpecError("UNRESP_CALL deve usare la modalita' CALL_112")

        color_tokens = spec.tokens["color_system"]["tokens"]
        for lane, control in controls.items():
            required = {
                "display_label",
                "semantic_event",
                "color_role",
                "touch_enabled",
                "physical_enabled",
            }
            if not isinstance(control, dict) or not required.issubset(control):
                raise UXSpecError(f"{state_id}/{lane}: controllo UX incompleto")
            if control["color_role"] not in color_tokens:
                raise UXSpecError(f"{state_id}/{lane}: color_role sconosciuto")
            if not control["display_label"] or not control["semantic_event"]:
                raise UXSpecError(f"{state_id}/{lane}: label/evento vuoto")
            if control["touch_enabled"] is not True or control["physical_enabled"] is not True:
                raise UXSpecError(f"{state_id}/{lane}: input touch/hardware non equivalenti")

            label = str(control["display_label"])
            role = str(control["color_role"])
            if node.get("type") == "decision" and label in {"NO", "SÌ"}:
                if role != "danger":
                    raise UXSpecError(
                        f"{state_id}/{lane}: NO e SÌ di valutazione devono avere lo stesso rosso"
                    )
            elif node.get("type") == "decision" and label == "NON SO":
                if role != "warning":
                    raise UXSpecError(f"{state_id}/{lane}: NON SO deve essere warning")
            elif node.get("type") == "decision_3" and role != "neutral":
                raise UXSpecError(f"{state_id}/{lane}: scelta categoriale non neutra")
            elif label in self.ACTION_COLOR_ROLES:
                expected_role = self.ACTION_COLOR_ROLES[label]
                if role != expected_role:
                    raise UXSpecError(
                        f"{state_id}/{lane}: {label} deve usare {expected_role}"
                    )

            source_label = control.get("source_button_label")
            if source_label is None:
                material_fallback = (
                    node.get("type") == "material_action_optional"
                    and lane == "left"
                    and control["semantic_event"] == EV_MATERIAL_NOT_FOUND
                )
                cpr_parallel_aed = (
                    state_id
                    in {
                        "ADULT_CPR",
                        "ADULT_CPR_LOOP",
                        "PED_CPR",
                        "PED_CPR_COMP_ONLY",
                    }
                    and control["semantic_event"] == EV_AED_AVAILABLE
                    and node.get("parallel_events", {}).get(EV_AED_AVAILABLE)
                    == "AED_USE"
                )
                if not (material_fallback or cpr_parallel_aed):
                    raise UXSpecError(
                        f"{state_id}/{lane}: evento presentazionale senza sorgente clinica"
                    )
                continue
            if source_label not in node["buttons"]:
                raise UXSpecError(
                    f"{state_id}/{lane}: pulsante sorgente assente nel flow"
                )
            expected_event = event_for_button(state_id, node, str(source_label))
            if expected_event != control["semantic_event"]:
                raise UXSpecError(
                    f"{state_id}/{lane}: evento UX {control['semantic_event']} "
                    f"diverso da {expected_event}"
                )

        if presentation.get("call112_policy_from_flow") != node.get("call112"):
            raise UXSpecError(f"{state_id}: policy 112 diversa dal flow")
        if presentation.get("material_led_zone_from_flow") != node.get("led_zone"):
            raise UXSpecError(f"{state_id}: zona LED diversa dal flow")

        repeat_mode = presentation.get("repeat_mode")
        repeat_controls = [
            lane
            for lane, control in controls.items()
            if control["semantic_event"] == EV_REPEAT
        ]
        if repeat_mode == "center_softkey":
            expected_count = 3 if EV_AED_AVAILABLE in {
                control["semantic_event"] for control in controls.values()
            } else 2
            if repeat_controls != ["center"] or len(controls) != expected_count:
                raise UXSpecError(f"{state_id}: RIPETI center non coerente")
        elif repeat_mode == "header_touch":
            if repeat_controls:
                raise UXSpecError(f"{state_id}: RIPETI header duplicato nelle lane")
        elif repeat_mode == "none":
            if repeat_controls:
                raise UXSpecError(f"{state_id}: RIPETI inatteso")
        else:
            raise UXSpecError(f"{state_id}: repeat_mode sconosciuto")

        expected_metronome = (
            "110_bpm_audio_visual" if node.get("metronome") else "off"
        )
        if presentation.get("cpr_metronome") != expected_metronome:
            raise UXSpecError(f"{state_id}: metronomo UX diverso dal flag del flow")
        self._validate_aed_control(spec, state_id, node, presentation)

    @staticmethod
    def _validate_aed_control(
        spec: UXSpec,
        state_id: str,
        node: dict[str, Any],
        presentation: dict[str, Any],
    ) -> None:
        cpr_states = {
            "ADULT_CPR",
            "ADULT_CPR_LOOP",
            "PED_CPR",
            "PED_CPR_COMP_ONLY",
        }
        post_aed_prompt = presentation.get("prompt_when_aed_present")
        control = presentation.get("aed_availability_control")
        if state_id not in cpr_states:
            if control is not None:
                raise UXSpecError(f"{state_id}: controllo DAE inatteso")
            if post_aed_prompt is not None:
                raise UXSpecError(f"{state_id}: prompt post-DAE inatteso")
            return
        source_mentions_availability = (
            "usa il dae appena disponibile" in str(node.get("prompt", "")).lower()
        )
        if source_mentions_availability:
            if not isinstance(post_aed_prompt, str) or not post_aed_prompt.strip():
                raise UXSpecError(f"{state_id}: prompt post-DAE mancante")
            if "appena disponibile" in post_aed_prompt.lower():
                raise UXSpecError(f"{state_id}: prompt post-DAE contraddittorio")
        elif post_aed_prompt is not None:
            raise UXSpecError(f"{state_id}: variante post-DAE non necessaria")
        required = {
            "display_label",
            "semantic_event",
            "color_role",
            "icon",
            "touch_enabled",
            "physical_enabled",
        }
        if not isinstance(control, dict) or not required.issubset(control):
            raise UXSpecError(f"{state_id}: controllo DAE incompleto")
        if control["color_role"] not in spec.tokens["color_system"]["tokens"]:
            raise UXSpecError(f"{state_id}: colore controllo DAE sconosciuto")

        target = node.get("parallel_events", {}).get(EV_AED_AVAILABLE)
        if control["semantic_event"] != EV_AED_AVAILABLE or target != "AED_USE":
            raise UXSpecError(f"{state_id}: evento DAE parallelo non coerente")
        if control["touch_enabled"] is not True:
            raise UXSpecError(f"{state_id}: CTA DAE touch non attiva")
        if control["physical_enabled"] is not True:
            raise UXSpecError(f"{state_id}: CTA DAE hardware non attiva")
        physical_lane = control.get("physical_lane")
        if physical_lane not in UXSpecLoader.LANES:
            raise UXSpecError(f"{state_id}: lane fisica DAE non valida")
        primary = presentation["primary_controls"].get(physical_lane, {})
        if primary.get("semantic_event") != EV_AED_AVAILABLE:
            raise UXSpecError(
                f"{state_id}: lane {physical_lane} non emette EV_AED_AVAILABLE"
            )
        if "hardware_equivalent" in control:
            raise UXSpecError(f"{state_id}: equivalenza hardware DAE ancora pending")

    def _validate_tokens(self, spec: UXSpec) -> None:
        lanes = spec.tokens.get("layout", {}).get("action_strip", {}).get("lanes")
        if lanes != list(self.LANES):
            raise UXSpecError("Le lane fisiche devono essere left/center/right")
        rule = spec.tokens.get("primary_control_rule", {})
        if rule.get("min_active") != 1 or rule.get("max_active") != 3:
            raise UXSpecError("La UX deve consentire da 1 a 3 controlli")
        tokens = spec.tokens.get("color_system", {}).get("tokens", {})
        for role in ("danger", "warning", "success", "support", "neutral", "category"):
            token = tokens.get(role, {})
            if self._contrast_ratio(token.get("bg"), token.get("fg")) < 4.5:
                raise UXSpecError(f"Contrasto insufficiente per il token {role}")

    @staticmethod
    def _validate_call112(spec: UXSpec) -> None:
        if spec.call112.get("manual_call_only") is not True:
            raise UXSpecError("La chiamata 112 deve restare manuale")
        required = {
            "CONDITIONAL",
            "RECOMMENDED",
            "RECOMMENDED_IMMEDIATE",
            "REQUIRED_PROMPT",
            "OPERATOR_PRIORITY",
            "USER_CALLING",
        }
        if set(spec.call112.get("policy_to_presentation", {})) != required:
            raise UXSpecError("Presentazioni 112 incomplete")
        items = spec.call112.get("call_briefing", {}).get("items", [])
        if [item.get("id") for item in items] != [
            "where",
            "what",
            "people",
            "condition",
            "hazards",
        ]:
            raise UXSpecError("Campi briefing 112 non validi")
        for item in items:
            if not str(item.get("fallback_prompt", "")).strip():
                raise UXSpecError(
                    f"Fallback briefing 112 mancante per {item.get('id')}"
                )
            display_fallback = str(item.get("display_fallback", "")).strip()
            if not display_fallback or len(display_fallback) > 40:
                raise UXSpecError(
                    f"Fallback display briefing 112 non valido per {item.get('id')}"
                )

    @staticmethod
    def _validate_cpr(spec: UXSpec, clinical: HandoffSpec) -> None:
        flow_enabled = {
            state_id
            for state_id, node in clinical.states.items()
            if node.get("metronome")
        }
        configured = set(spec.cpr.get("enabled_states", []))
        if configured != flow_enabled:
            raise UXSpecError("Stati metronomo diversi dal Flow 1.2")
        metronome = spec.cpr.get("metronome", {})
        if metronome.get("target_bpm") != 110:
            raise UXSpecError("Il target UX del metronomo deve essere 110 bpm")
        if spec.cpr.get("cycle_management", {}).get("automatic_30_2_timing") is not False:
            raise UXSpecError("La UX non puo' introdurre gestione automatica 30:2")

    @classmethod
    def _contrast_ratio(cls, background: Any, foreground: Any) -> float:
        bg = cls._relative_luminance(str(background))
        fg = cls._relative_luminance(str(foreground))
        lighter, darker = max(bg, fg), min(bg, fg)
        return (lighter + 0.05) / (darker + 0.05)

    @staticmethod
    def _relative_luminance(value: str) -> float:
        if len(value) != 7 or not value.startswith("#"):
            raise UXSpecError(f"Colore non valido: {value}")
        channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
