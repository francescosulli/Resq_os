from __future__ import annotations

from resq_core.logger import get_logger


class AudioGuide:
    def __init__(self) -> None:
        self.logger = get_logger("hardware.audio")
        self.playback_count = 0
        self.stop_count = 0
        self.current_instruction = ""

    def play_instruction(self, text: str) -> str:
        self.playback_count += 1
        self.current_instruction = text
        message = f"[AUDIO] {text}"
        self.logger.info(message)
        return message

    def stop_instruction(self) -> str:
        self.stop_count += 1
        self.current_instruction = ""
        message = "[AUDIO] Stop istruzione"
        self.logger.info(message)
        return message

    def test(self) -> str:
        message = "[AUDIO] Test guida audio simulata completato"
        self.logger.info(message)
        return message
