from __future__ import annotations

from resq_core.logger import get_logger


class LEDController:
    def __init__(self) -> None:
        self.logger = get_logger("hardware.leds")
        self.current_compartment = ""
        self.current_led_id = ""

    def highlight_zone(self, zone_id: str, led_id: str) -> str:
        self.current_compartment = zone_id
        self.current_led_id = led_id
        message = f"[LED] Accendo zona {zone_id} tramite {led_id}"
        self.logger.info(message)
        return message

    def highlight_compartment(self, compartment_name: str) -> str:
        self.current_compartment = compartment_name
        self.current_led_id = ""
        message = f"[LED] Accendo perimetro vano: {compartment_name}"
        self.logger.info(message)
        return message

    def clear(self) -> str:
        self.current_compartment = ""
        self.current_led_id = ""
        message = "[LED] Spengo perimetri vani"
        self.logger.info(message)
        return message

    def test_sequence(self) -> str:
        message = "[LED] Test sequenza perimetrale completato"
        self.logger.info(message)
        return message
