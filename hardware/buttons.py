from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from time import monotonic
from typing import Any

from resq_core.logger import get_logger


class ButtonController:
    DEBOUNCE_SECONDS = 0.14
    BUTTON_MAP = {
        "left": "left",
        "soft_key_left": "left",
        "1": "left",
        "center": "center",
        "centre": "center",
        "soft_key_center": "center",
        "2": "center",
        "right": "right",
        "soft_key_right": "right",
        "3": "right",
    }

    def __init__(self) -> None:
        self.logger = get_logger("hardware.buttons")
        self._lock = RLock()
        self._active_lanes: dict[str, str] = {}
        self._last_press_at = 0.0
        self._feedback: dict[str, Any] = {
            "sequence": 0,
            "lane": None,
            "event": None,
            "pressed_at": None,
        }

    def configure_soft_keys(self, soft_keys: list[dict[str, Any]]) -> None:
        active_lanes: dict[str, str] = {}
        for key in soft_keys:
            lane = str(key.get("lane") or key.get("position") or "")
            event = str(key.get("event", ""))
            if lane in {"left", "center", "right"} and event:
                active_lanes[lane] = event
        with self._lock:
            self._active_lanes = active_lanes

    def event_for_lane(self, lane: str) -> str | None:
        with self._lock:
            return self._active_lanes.get(lane)

    def record_press(self, lane: str, event: str) -> bool:
        with self._lock:
            now = monotonic()
            if now - self._last_press_at < self.DEBOUNCE_SECONDS:
                return False
            self._last_press_at = now
            self._feedback = {
                "sequence": int(self._feedback["sequence"]) + 1,
                "lane": lane,
                "event": event,
                "pressed_at": datetime.now(timezone.utc).isoformat(),
            }
            return True

    def feedback_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._feedback)

    def handle_button(self, button_name: str) -> str | None:
        canonical = self.BUTTON_MAP.get(button_name.lower())
        if not canonical:
            self.logger.warning("[BUTTON] Pulsante non riconosciuto: %s", button_name)
            return None
        self.logger.info("[BUTTON] Premuto: %s -> %s", button_name, canonical)
        return canonical
