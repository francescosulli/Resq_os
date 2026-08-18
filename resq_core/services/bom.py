from __future__ import annotations

import copy
from typing import Any, Callable


class BOMError(ValueError):
    """Raised when a semantic request cannot be resolved against the BOM."""


class BOMCatalog:
    REQUEST_QUANTITY_OVERRIDES = {
        "PPE_GLOVES": 2,
    }

    def __init__(self, bom: dict[str, Any]) -> None:
        self.version = str(bom["bom_version"])
        self.product_profile = str(bom["product_profile"])
        self.items = copy.deepcopy(bom["items"])
        self.zones = copy.deepcopy(bom["zones"])
        self.material_requests = copy.deepcopy(bom["material_requests"])

    def expected_stock(self) -> dict[str, int]:
        return {
            sku: int(item["quantity_expected"])
            for sku, item in self.items.items()
        }

    def preferred_sku(self, request_id: str) -> str:
        request = self._request(request_id)
        return str(request["preferred"][0])

    def candidates(self, request_id: str) -> list[str]:
        request = self._request(request_id)
        return [
            str(sku)
            for sku in list(request.get("preferred", []))
            + list(request.get("fallback", []))
        ]

    def resolve(
        self,
        request_id: str,
        available_quantity: Callable[[str], int],
        excluded_skus: set[str] | None = None,
    ) -> dict[str, Any] | None:
        request = self._request(request_id)
        excluded = excluded_skus or set()
        preferred_count = len(request.get("preferred", []))
        policy = str(request.get("selection_policy", "single"))

        for index, sku in enumerate(self.candidates(request_id)):
            if sku in excluded:
                continue
            available = max(0, int(available_quantity(sku)))
            if available == 0:
                continue

            requested_quantity = self.REQUEST_QUANTITY_OVERRIDES.get(
                request_id,
                2 if policy == "quantity_required_2_if_available" else 1,
            )
            if request_id in self.REQUEST_QUANTITY_OVERRIDES and available < requested_quantity:
                continue
            quantity = min(requested_quantity, available)
            item = self.items[sku]
            zone_id = str(item["zone"])
            zone = self.zones[zone_id]
            return copy.deepcopy(
                {
                    "material_id": request_id,
                    "sku": sku,
                    "name_it": item["name_it"],
                    "quantity": quantity,
                    "unit": item["unit"],
                    "zone": zone_id,
                    "zone_name_it": zone["name_it"],
                    "slot": item["slot"],
                    "led_id": zone["led_id"],
                    "fallback_used": index >= preferred_count,
                    "candidate_index": index,
                    "selection_policy": policy,
                }
            )
        return None

    def item_summary(self, sku: str, quantity: int = 1) -> dict[str, Any]:
        try:
            item = self.items[sku]
        except KeyError as exc:
            raise BOMError(f"SKU BOM sconosciuto: {sku}") from exc
        zone_id = str(item["zone"])
        zone = self.zones[zone_id]
        return copy.deepcopy(
            {
                "sku": sku,
                "name_it": item["name_it"],
                "quantity": int(quantity),
                "unit": item["unit"],
                "zone": zone_id,
                "zone_name_it": zone["name_it"],
                "slot": item["slot"],
                "led_id": zone["led_id"],
            }
        )

    def _request(self, request_id: str) -> dict[str, Any]:
        try:
            return self.material_requests[request_id]
        except KeyError as exc:
            raise BOMError(f"MaterialRequest BOM sconosciuta: {request_id}") from exc
