from __future__ import annotations

from resq_core.logger import get_logger


class NFCReader:
    def __init__(self) -> None:
        self.logger = get_logger("hardware.nfc")

    def simulate_read(self, expected_item: str) -> str:
        message = f"[NFC] Oggetto rilevato: {expected_item}"
        self.logger.info(message)
        return expected_item

    def test(self) -> str:
        message = "[NFC] Test lettore simulato completato"
        self.logger.info(message)
        return message

