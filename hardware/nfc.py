from __future__ import annotations

from resq_core.logger import get_logger


class NFCReader:
    def __init__(self) -> None:
        self.logger = get_logger("hardware.nfc")

    def simulate_refill(self, item_name: str) -> str:
        message = f"[NFC REFILL] Refill rilevato: {item_name}"
        self.logger.info(message)
        return item_name

    def test(self) -> str:
        message = "[NFC REFILL] Test lettore refill simulato completato"
        self.logger.info(message)
        return message
