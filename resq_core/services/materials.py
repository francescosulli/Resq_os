from __future__ import annotations

import copy
from typing import Any, Callable

from hardware.leds import LEDController
from resq_core.services.bom import BOMCatalog


class MaterialService:
    def __init__(
        self,
        catalog: BOMCatalog,
        leds: LEDController,
        available_quantity: Callable[[str], int],
    ) -> None:
        self.catalog = catalog
        self.leds = leds
        self.available_quantity = available_quantity
        self.reset()

    def reset(self) -> None:
        self.state = "IDLE"
        self.active_request: dict[str, Any] | None = None
        self.active_led_zone: str | None = None
        self.active_led_id: str | None = None
        self.unavailable_skus: set[str] = set()
        self.led_message = self.leds.clear()

    def enter_state(self, node: dict[str, Any]) -> None:
        material_ids = list(node.get("materials", []))
        if not material_ids:
            self._clear_active_request()
            return
        if len(material_ids) != 1:
            raise ValueError("MaterialService accetta una sola MaterialRequest per stato")

        request_id = str(material_ids[0])
        self.state = "REQUESTED"
        self._resolve_and_activate(request_id)

    def report_not_found(self) -> bool:
        if not self.active_request:
            return False
        request_id = str(self.active_request["material_id"])
        resolved = self.active_request.get("resolved")
        if resolved:
            self.unavailable_skus.add(str(resolved["sku"]))
        return self._resolve_and_activate(request_id)

    def take_active(self) -> list[dict[str, Any]]:
        if not self.active_request or not self.active_request.get("resolved"):
            return []
        self.state = "FOUND"
        return [copy.deepcopy(self.active_request["resolved"])]

    def skip_active(self) -> None:
        self._clear_active_request()

    def restore(self, snapshot: dict[str, Any]) -> None:
        self.state = str(snapshot.get("state", "IDLE"))
        self.active_request = copy.deepcopy(snapshot.get("active_request"))
        if self.active_request is None:
            legacy_requests = snapshot.get("active_requests", [])
            if legacy_requests:
                material_id = legacy_requests[0].get("material_id")
                self.active_request = {
                    "material_id": material_id,
                    "resolved": None,
                }
        self.active_led_zone = snapshot.get("active_led_zone")
        self.active_led_id = snapshot.get("active_led_id")
        self.unavailable_skus = set(snapshot.get("unavailable_skus", []))
        self.led_message = str(snapshot.get("led_message", ""))
        if self.active_led_zone and self.active_led_id:
            self.led_message = self.leds.highlight_zone(
                self.active_led_zone,
                self.active_led_id,
            )
        else:
            self.led_message = self.leds.clear()

    def snapshot(self) -> dict[str, Any]:
        active_requests = [self.active_request] if self.active_request else []
        return copy.deepcopy(
            {
                "state": self.state,
                "bom_version": self.catalog.version,
                "kit_profile": self.catalog.product_profile,
                "active_request": self.active_request,
                "active_requests": active_requests,
                "active_led_zone": self.active_led_zone,
                "active_led_id": self.active_led_id,
                "unavailable_skus": sorted(self.unavailable_skus),
                "led_message": self.led_message,
            }
        )

    def _resolve_and_activate(self, request_id: str) -> bool:
        resolved = self.catalog.resolve(
            request_id,
            self.available_quantity,
            self.unavailable_skus,
        )
        self.active_request = {
            "material_id": request_id,
            "resolved": resolved,
        }
        if resolved is None:
            self.state = "UNAVAILABLE"
            self.active_led_zone = None
            self.active_led_id = None
            self.led_message = self.leds.clear()
            return False

        self.state = "LED_ON"
        self.active_led_zone = str(resolved["zone"])
        self.active_led_id = str(resolved["led_id"])
        self.led_message = self.leds.highlight_zone(
            self.active_led_zone,
            self.active_led_id,
        )
        self.state = "WAIT_CONFIRM"
        return True

    def _clear_active_request(self) -> None:
        self.state = "IDLE"
        self.active_request = None
        self.active_led_zone = None
        self.active_led_id = None
        self.led_message = self.leds.clear()
