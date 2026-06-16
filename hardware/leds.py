from __future__ import annotations

from resq_core.logger import get_logger


class LEDController:
    def __init__(self) -> None:
        self.logger = get_logger("hardware.leds")
        self.current_compartment = ""

    def highlight_compartment(self, compartment_name: str) -> str:
        self.current_compartment = compartment_name
        message = f"[LED] Accendo perimetro vano: {compartment_name}"
        self.logger.info(message)
        return message

    def clear(self) -> str:
        self.current_compartment = ""
        message = "[LED] Spengo perimetri vani"
        self.logger.info(message)
        return message

    def test_sequence(self) -> str:
        message = "[LED] Test sequenza perimetrale completato"
        self.logger.info(message)
        return message

