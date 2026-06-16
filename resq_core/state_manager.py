from __future__ import annotations

import copy
from datetime import datetime, timezone
from threading import RLock
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateManager:
    def __init__(self) -> None:
        self._lock = RLock()
        self._state = self._blank_state("home")

    def _blank_state(self, mode: str) -> dict[str, Any]:
        return {
            "mode": mode,
            "protocol_id": None,
            "current_step_id": None,
            "history": [],
            "answers": [],
            "requested_items": [],
            "nfc_events": [],
            "started_at": None,
            "completed_at": None,
            "last_audio_text": "",
            "active_item": None,
            "last_answer_message": "",
            "summary": "",
            "led_status": {
                "active": False,
                "compartment": "",
                "message": "[LED] Perimetri spenti",
            },
            "nfc_status": {
                "status": "idle",
                "message": "[NFC] In attesa",
                "expected_item": "",
                "detected_item": "",
            },
        }

    def reset_home(self) -> dict[str, Any]:
        with self._lock:
            self._state = self._blank_state("home")
            return self.snapshot()

    def start_emergency(self) -> dict[str, Any]:
        with self._lock:
            self._state = self._blank_state("selecting")
            return self.snapshot()

    def start_protocol(self, protocol_id: str, first_step: str) -> None:
        with self._lock:
            self._state = self._blank_state("protocol")
            self._state["protocol_id"] = protocol_id
            self._state["current_step_id"] = first_step
            self._state["started_at"] = utc_now()

    def transition_to(self, step_id: str, push_history: bool = True) -> None:
        with self._lock:
            current = self._state.get("current_step_id")
            if push_history and current:
                self._state["history"].append(current)
            self._state["mode"] = "protocol"
            self._state["current_step_id"] = step_id
            self._state["last_answer_message"] = ""
            self._state["active_item"] = None
            self._state["nfc_status"] = {
                "status": "idle",
                "message": "[NFC] In attesa",
                "expected_item": "",
                "detected_item": "",
            }

    def back(self) -> str | None:
        with self._lock:
            if not self._state["history"]:
                return None
            previous = self._state["history"].pop()
            self._state["mode"] = "protocol"
            self._state["current_step_id"] = previous
            self._state["active_item"] = None
            self._state["summary"] = ""
            self._state["completed_at"] = None
            return previous

    def record_answer(self, question: str, answer: str) -> None:
        with self._lock:
            self._state["answers"].append(
                {
                    "question": question,
                    "answer": answer,
                    "at": utc_now(),
                }
            )

    def set_last_answer_message(self, message: str) -> None:
        with self._lock:
            self._state["last_answer_message"] = message

    def set_audio(self, text: str) -> None:
        with self._lock:
            self._state["last_audio_text"] = text

    def set_led_status(self, active: bool, compartment: str, message: str) -> None:
        with self._lock:
            self._state["led_status"] = {
                "active": active,
                "compartment": compartment,
                "message": message,
            }

    def set_active_item(self, item: dict[str, str]) -> None:
        with self._lock:
            self._state["active_item"] = item

    def record_item_requested(self, item: dict[str, str]) -> None:
        with self._lock:
            self._state["requested_items"].append(
                {
                    "name": item["name"],
                    "compartment": item["compartment"],
                    "nfc_tag": item["nfc_tag"],
                    "at": utc_now(),
                }
            )

    def set_nfc_status(
        self,
        status: str,
        message: str,
        expected_item: str = "",
        detected_item: str = "",
    ) -> None:
        with self._lock:
            self._state["nfc_status"] = {
                "status": status,
                "message": message,
                "expected_item": expected_item,
                "detected_item": detected_item,
            }

    def record_nfc(self, expected_item: str, detected_item: str, ok: bool) -> None:
        with self._lock:
            self._state["nfc_events"].append(
                {
                    "expected_item": expected_item,
                    "detected_item": detected_item,
                    "ok": ok,
                    "at": utc_now(),
                }
            )

    def complete(self, summary: str) -> None:
        with self._lock:
            self._state["mode"] = "completed"
            self._state["summary"] = summary
            self._state["completed_at"] = utc_now()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

