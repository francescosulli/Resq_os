from __future__ import annotations

import copy
from typing import Any


class EmergencyBriefContext:
    """Read-only-to-clinical cache of observations explicitly supplied by the user."""

    ALLOWED_FIELDS = {
        "scene_safety_observation",
        "multiple_casualties_observation",
        "major_bleeding_observation",
        "responsiveness_observation",
        "breathing_observation",
        "age_class",
        "current_state_family",
        "user_entered_location_if_available",
    }

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.observations: dict[str, str | None] = {
            field: None for field in sorted(self.ALLOWED_FIELDS)
        }

    def observe(self, previous_state: str, event: str, current_state: str) -> None:
        value = self._observation_for(previous_state, event)
        if value:
            field, text = value
            self.observations[field] = text
        family = self._state_family_for(previous_state, event, current_state)
        if family:
            self.observations["current_state_family"] = family

    def restore(self, snapshot: dict[str, Any]) -> None:
        restored = snapshot.get("observations", {})
        if not isinstance(restored, dict):
            restored = {}
        self.observations = {
            field: self._clean_value(restored.get(field))
            for field in sorted(self.ALLOWED_FIELDS)
        }

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "type": "read_only_observation_cache",
                "must_not_affect_clinical_transitions": True,
                "observations": self.observations,
                "briefing_values": self._briefing_values(),
                "briefing_compact": self._briefing_compact(),
            }
        )

    def _briefing_compact(self) -> dict[str, str | None]:
        short_values = {
            "La persona non risponde o non reagisce.": "Non risponde",
            "La persona risponde o reagisce.": "Risponde",
            "La respirazione non è normale o resta incerta.": "Respirazione non normale",
            "È stata osservata respirazione normale.": "Respira normalmente",
            "È stato segnalato un sanguinamento molto abbondante.": "Sanguinamento importante",
            "Non è stato segnalato un sanguinamento molto abbondante.": "Nessun sanguinamento importante segnalato",
            "Adulto.": "Adulto",
            "Bambino.": "Bambino",
            "Lattante.": "Lattante",
            "Sono state segnalate più persone coinvolte; il numero esatto non è noto.": "Più persone coinvolte",
            "La scena è stata indicata come sicura.": "Scena indicata come sicura",
            "Sono stati segnalati pericoli sulla scena; descrivili all'operatore.": "Pericoli presenti",
            "La sicurezza della scena non è stata confermata.": "Sicurezza della scena incerta",
        }
        condition_fields = (
            "responsiveness_observation",
            "breathing_observation",
            "major_bleeding_observation",
            "age_class",
        )
        condition = [
            short_values.get(str(self.observations[field]), self.observations[field])
            for field in condition_fields
            if self.observations[field]
        ]
        family = self.observations["current_state_family"]
        return {
            "where": self.observations["user_entered_location_if_available"],
            "what": family.rstrip(".") if family else None,
            "people": short_values.get(
                str(self.observations["multiple_casualties_observation"]),
                self.observations["multiple_casualties_observation"],
            ),
            "condition": " · ".join(str(value) for value in condition) or None,
            "hazards": short_values.get(
                str(self.observations["scene_safety_observation"]),
                self.observations["scene_safety_observation"],
            ),
        }

    def _briefing_values(self) -> dict[str, str | None]:
        condition_parts = [
            self.observations["responsiveness_observation"],
            self.observations["breathing_observation"],
            self.observations["major_bleeding_observation"],
            self.observations["age_class"],
        ]
        return {
            "where": self.observations["user_entered_location_if_available"],
            "what": self.observations["current_state_family"],
            "people": self.observations["multiple_casualties_observation"],
            "condition": " ".join(part for part in condition_parts if part) or None,
            "hazards": self.observations["scene_safety_observation"],
        }

    @staticmethod
    def _clean_value(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _observation_for(previous_state: str, event: str) -> tuple[str, str] | None:
        observations = {
            ("SCENE_SAFE", "EV_YES"): (
                "scene_safety_observation",
                "La scena è stata indicata come sicura.",
            ),
            ("SCENE_SAFE", "EV_NO"): (
                "scene_safety_observation",
                "Sono stati segnalati pericoli sulla scena; descrivili all'operatore.",
            ),
            ("SCENE_SAFE", "EV_UNKNOWN"): (
                "scene_safety_observation",
                "La sicurezza della scena non è stata confermata.",
            ),
            ("SCENE_RECHECK", "EV_YES"): (
                "scene_safety_observation",
                "La scena è stata rivalutata come sicura.",
            ),
            ("SCENE_RECHECK", "EV_NO"): (
                "scene_safety_observation",
                "I pericoli sulla scena risultano ancora presenti.",
            ),
            ("SCENE_RECHECK", "EV_UNKNOWN"): (
                "scene_safety_observation",
                "La sicurezza della scena resta incerta.",
            ),
            ("MULTI_CASUALTY", "EV_YES"): (
                "multiple_casualties_observation",
                "Sono state segnalate più persone coinvolte; il numero esatto non è noto.",
            ),
            ("MULTI_CASUALTY", "EV_NO"): (
                "multiple_casualties_observation",
                "Non sono state segnalate più persone; conferma il numero all'operatore.",
            ),
            ("MULTI_CASUALTY", "EV_UNKNOWN"): (
                "multiple_casualties_observation",
                "Il numero di persone coinvolte non è stato confermato.",
            ),
            ("MASSIVE_BLEED", "EV_YES"): (
                "major_bleeding_observation",
                "È stato segnalato un sanguinamento molto abbondante.",
            ),
            ("MASSIVE_BLEED", "EV_NO"): (
                "major_bleeding_observation",
                "Non è stato segnalato un sanguinamento molto abbondante.",
            ),
            ("MASSIVE_BLEED", "EV_UNKNOWN"): (
                "major_bleeding_observation",
                "La presenza di sanguinamento importante non è stata confermata.",
            ),
            ("RESPONSIVE", "EV_RESPONSIVE"): (
                "responsiveness_observation",
                "La persona risponde o reagisce.",
            ),
            ("RESPONSIVE", "EV_UNRESPONSIVE"): (
                "responsiveness_observation",
                "La persona non risponde o non reagisce.",
            ),
            ("ADULT_BREATH_CHECK", "EV_NORMAL_BREATHING"): (
                "breathing_observation",
                "È stata osservata respirazione normale.",
            ),
            ("ADULT_BREATH_CHECK", "EV_ABNORMAL_BREATHING"): (
                "breathing_observation",
                "La respirazione non è normale o resta incerta.",
            ),
            ("PED_BREATH_CHECK", "EV_NORMAL_BREATHING"): (
                "breathing_observation",
                "È stata osservata respirazione normale.",
            ),
            ("PED_BREATH_CHECK", "EV_ABNORMAL_BREATHING"): (
                "breathing_observation",
                "La respirazione non è normale o resta incerta.",
            ),
            ("AGE_BLS", "EV_SELECT_INFANT"): ("age_class", "Lattante."),
            ("AGE_BLS", "EV_SELECT_CHILD"): ("age_class", "Bambino."),
            ("AGE_BLS", "EV_SELECT_ADULT"): ("age_class", "Adulto."),
        }
        return observations.get((previous_state, event))

    @staticmethod
    def _state_family_for(
        previous_state: str,
        event: str,
        current_state: str,
    ) -> str | None:
        explicit = {
            ("C_CIRCULATION", "EV_SELECT_SANGUE"): "È stato segnalato un problema di sanguinamento.",
            ("C_CIRCULATION", "EV_SELECT_MALORE"): "È stato segnalato un malore.",
            ("E_EXPOSURE", "EV_SELECT_TRAUMA"): "È stato segnalato un trauma.",
            ("E_EXPOSURE", "EV_SELECT_USTIONE_AMBIENTE"): "È stato segnalato un problema ambientale o un'ustione.",
            ("TRAUMA_SELECT", "EV_SELECT_FERITA"): "È stata segnalata una ferita.",
            ("TRAUMA_SELECT", "EV_SELECT_ARTO"): "È stato segnalato un trauma a un arto.",
            ("TRAUMA_SELECT", "EV_SELECT_TESTA_TORACE"): "È stato segnalato un trauma a testa o torace.",
            ("ENV_SELECT", "EV_SELECT_USTIONE"): "È stata segnalata un'ustione.",
            ("ENV_SELECT", "EV_SELECT_FREDDO"): "È stato segnalato un problema da freddo.",
        }
        selected = explicit.get((previous_state, event))
        if selected:
            return selected
        if current_state in {"BLEED_DIRECT_PRESSURE", "TOURNIQUET", "HEMOSTATIC"}:
            return "È stato segnalato un sanguinamento importante."
        return None
