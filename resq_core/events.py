from __future__ import annotations

import re
import unicodedata
from typing import Any


EV_START_EMERGENCY = "EV_START_EMERGENCY"
EV_AED_AVAILABLE = "EV_AED_AVAILABLE"
EV_YES = "EV_YES"
EV_NO = "EV_NO"
EV_UNKNOWN = "EV_UNKNOWN"
EV_DONE = "EV_DONE"
EV_REPEAT = "EV_REPEAT"
EV_PROBLEM = "EV_PROBLEM"
EV_MATERIAL_NOT_FOUND = "EV_MATERIAL_NOT_FOUND"
EV_MATERIAL_TAKEN = "EV_MATERIAL_TAKEN"
EV_MATERIAL_UNAVAILABLE = "EV_MATERIAL_UNAVAILABLE"
EV_ITEM_TAKEN = "EV_ITEM_TAKEN"
EV_SKIP = "EV_SKIP"
EV_CALL112_STARTED = "EV_CALL112_STARTED"
EV_OPERATOR_ACTIVE = "EV_OPERATOR_ACTIVE"
EV_OPERATOR_ENDED = "EV_OPERATOR_ENDED"
EV_RESPONSIVE = "EV_RESPONSIVE"
EV_UNRESPONSIVE = "EV_UNRESPONSIVE"
EV_NORMAL_BREATHING = "EV_NORMAL_BREATHING"
EV_ABNORMAL_BREATHING = "EV_ABNORMAL_BREATHING"
EV_WORSENING = "EV_WORSENING"
EV_STABLE = "EV_STABLE"
EV_HANDOVER = "EV_HANDOVER"
EV_CLOSE_SESSION = "EV_CLOSE_SESSION"
EV_RESUME_SESSION = "EV_RESUME_SESSION"
EV_DISCARD_SESSION = "EV_DISCARD_SESSION"


def event_for_button(state_id: str, node: dict[str, Any], label: str) -> str | None:
    if not label:
        return None

    if state_id == "RESPONSIVE":
        if label == "SÌ":
            return EV_RESPONSIVE
        if label in {"NO", "NON SO"}:
            return EV_UNRESPONSIVE

    if state_id in {"ADULT_BREATH_CHECK", "PED_BREATH_CHECK"}:
        if label == "SÌ":
            return EV_NORMAL_BREATHING
        if label in {"NO", "NON SO"}:
            return EV_ABNORMAL_BREATHING

    if state_id == "UNRESP_CALL" and label == "FATTO":
        return EV_CALL112_STARTED

    if label == "FATTO" and node.get("materials"):
        return EV_MATERIAL_TAKEN

    direct = {
        "NO": EV_NO,
        "NON SO": EV_UNKNOWN,
        "SÌ": EV_YES,
        "INIZIA": EV_START_EMERGENCY,
        "ESCI": EV_CLOSE_SESSION,
        "PROBLEMA": EV_PROBLEM,
        "CORREGGI": EV_PROBLEM,
        "RIPETI": EV_REPEAT,
        "MOSTRA": EV_REPEAT,
        "RIVEDI": EV_REPEAT,
        "FATTO": EV_DONE,
        "CONTINUA": EV_DONE,
        "RIVALUTA": EV_DONE,
        "NON TROVO": EV_MATERIAL_NOT_FOUND,
        "PRESO": EV_ITEM_TAKEN,
        "SALTA": EV_SKIP,
        "PEGGIORA": EV_WORSENING,
        "RESPIRA": EV_NORMAL_BREATHING,
        "RISOLTO": EV_STABLE,
        "STABILE": EV_STABLE,
        "CHIUDI": EV_HANDOVER,
        "CONFERMA": EV_CLOSE_SESSION,
        "HOME": EV_CLOSE_SESSION,
        "LATTANTE": "EV_SELECT_INFANT",
        "BAMBINO": "EV_SELECT_CHILD",
        "ADULTO": "EV_SELECT_ADULT",
    }
    if label in direct:
        return direct[label]
    return f"EV_SELECT_{_event_slug(label)}"


def soft_keys_for(state_id: str, node: dict[str, Any]) -> list[dict[str, Any]]:
    positions = ("left", "center", "right")
    return [
        {
            "position": position,
            "label": label,
            "event": event_for_button(state_id, node, label),
            "enabled": bool(label),
        }
        for position, label in zip(positions, node["buttons"])
    ]


def _event_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]+", "_", ascii_value.upper()).strip("_")
