from __future__ import annotations

from resq_core.logger import get_logger


class DisplayManager:
    def __init__(self) -> None:
        self.logger = get_logger("hardware.display")

    def prepare_fullscreen(self) -> str:
        message = "[DISPLAY] Modalita' fullscreen/kiosk predisposta"
        self.logger.info(message)
        return message

