from __future__ import annotations

from resq_core.logger import get_logger


class AudioGuide:
    def __init__(self) -> None:
        self.logger = get_logger("hardware.audio")

    def play_instruction(self, text: str) -> str:
        message = f"[AUDIO] {text}"
        self.logger.info(message)
        return message

    def test(self) -> str:
        message = "[AUDIO] Test guida audio simulata completato"
        self.logger.info(message)
        return message

