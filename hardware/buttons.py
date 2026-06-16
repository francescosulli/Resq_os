from __future__ import annotations

from resq_core.logger import get_logger


class ButtonController:
    BUTTON_MAP = {
        "yes": "yes",
        "y": "yes",
        "s": "yes",
        "si": "yes",
        "no": "no",
        "n": "no",
        "back": "back",
        "indietro": "back",
        "repeat_audio": "repeat_audio",
        "repeat": "repeat_audio",
        "audio": "repeat_audio",
        "home": "home_emergency",
        "emergency": "home_emergency",
        "home_emergency": "home_emergency",
    }

    def __init__(self) -> None:
        self.logger = get_logger("hardware.buttons")

    def handle_button(self, button_name: str) -> str:
        canonical = self.BUTTON_MAP.get(button_name.lower())
        if not canonical:
            self.logger.warning("[BUTTON] Pulsante non riconosciuto: %s", button_name)
            return button_name
        self.logger.info("[BUTTON] Premuto: %s -> %s", button_name, canonical)
        return canonical

