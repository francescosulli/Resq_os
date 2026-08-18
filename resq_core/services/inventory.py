from __future__ import annotations

import copy
from datetime import date
from typing import Any

from resq_core.services.bom import BOMCatalog, BOMError
from resq_core.services.inventory_instance import (
    AVAILABLE,
    INVENTORY_STATUSES,
    MISSING,
    PENDING_USE,
    SUSPECTED_MISSING,
    USED,
    InventoryInstance,
)
from resq_core.services.readiness import DEFAULT_READINESS_POLICY, ReadinessPolicy


class InventoryService:
    """Owns mutable case inventory; the BOM remains an immutable catalog."""

    def __init__(
        self,
        catalog: BOMCatalog,
        readiness_policy: ReadinessPolicy | None = None,
    ) -> None:
        self.catalog = catalog
        self.readiness_policy = readiness_policy or DEFAULT_READINESS_POLICY
        self.reset()

    def reset(self) -> None:
        self.state = "READY"
        self.instances = {
            sku: InventoryInstance.create(sku, int(item["quantity_expected"]))
            for sku, item in self.catalog.items.items()
        }
        self.pending_use: dict[str, int] = {}
        self.pending_material_requests: set[str] = set()
        self.suspected_missing: set[str] = set()
        self.review_candidates: set[str] = set()
        self.correction_enabled = False
        self.used: dict[str, int] = {}
        self.local_dirty = False
        self._validate_all()

    @property
    def stock(self) -> dict[str, int]:
        return {
            sku: instance.quantity_available
            for sku, instance in self.instances.items()
        }

    def available_quantity(self, sku: str) -> int:
        instance = self._instance(sku)
        instance.refresh_expiry(self._tracks_expiry(sku))
        if instance.status not in {AVAILABLE, PENDING_USE}:
            return 0
        return max(
            0,
            int(instance.quantity_available) - int(self.pending_use.get(sku, 0)),
        )

    def set_stock(self, sku: str, quantity: int) -> None:
        if sku in self.pending_use or sku in self.suspected_missing:
            raise ValueError(f"Stock {sku} non modificabile durante una revisione")
        instance = self._instance(sku)
        expected = self._quantity_expected(sku)
        if not 0 <= quantity <= expected:
            raise ValueError(
                f"Quantita' inventario fuori limite per {sku}: {quantity}/{expected}"
            )
        instance.quantity_available = int(quantity)
        instance.status = AVAILABLE if quantity > 0 else MISSING
        instance.suspected_quantity = 0
        instance.touch()
        self.suspected_missing.discard(sku)
        self._validate_instance(sku)

    def mark_pending(self, resolved_items: list[dict[str, Any]]) -> None:
        for item in resolved_items:
            sku = str(item["sku"])
            quantity = int(item.get("quantity", 1))
            if quantity < 1 or quantity > self.available_quantity(sku):
                raise ValueError(f"Quantita' non disponibile per {sku}: {quantity}")
            self.pending_use[sku] = self.pending_use.get(sku, 0) + quantity
            instance = self._instance(sku)
            instance.status = PENDING_USE
            instance.touch()
            material_id = item.get("material_id")
            if material_id:
                self.pending_material_requests.add(str(material_id))
            self._validate_instance(sku)
        if self.pending_use:
            self.state = "PENDING_USE"

    def mark_suspected_missing(self, resolved_item: dict[str, Any]) -> None:
        sku = str(resolved_item["sku"])
        instance = self._instance(sku)
        if instance.status == SUSPECTED_MISSING:
            return
        instance.suspected_quantity = instance.quantity_available
        instance.quantity_available = 0
        instance.status = SUSPECTED_MISSING
        instance.touch()
        self.suspected_missing.add(sku)
        self.review_candidates.add(sku)
        self.local_dirty = True
        self.state = SUSPECTED_MISSING
        self._validate_instance(sku)

    def begin_review(self) -> None:
        self.state = "POST_EVENT_REVIEW"
        self.review_candidates.update(self.pending_use)
        self.review_candidates.update(self.suspected_missing)

    def enable_correction(self) -> None:
        self.begin_review()
        self.correction_enabled = True

    def correct_pending(self, sku: str, quantity: int) -> None:
        instance = self._instance(sku)
        maximum = self._quantity_expected(sku)
        if quantity < 0 or quantity > maximum:
            raise ValueError(f"Quantita' di correzione non valida per {sku}")

        if sku in self.suspected_missing or instance.status == SUSPECTED_MISSING:
            instance.quantity_available = int(quantity)
            instance.status = AVAILABLE if quantity > 0 else MISSING
            instance.suspected_quantity = 0
            instance.touch()
            self.suspected_missing.discard(sku)
            self.local_dirty = True
        elif sku in self.pending_use or sku in self.review_candidates:
            if quantity > instance.quantity_available:
                raise ValueError(f"Quantita' di correzione non valida per {sku}")
            if quantity == 0:
                self.pending_use.pop(sku, None)
                instance.status = AVAILABLE if instance.quantity_available else USED
            else:
                self.pending_use[sku] = int(quantity)
                instance.status = PENDING_USE
            instance.touch()
        else:
            raise ValueError(f"SKU {sku} non presente nella revisione post-evento")

        self.review_candidates.add(sku)
        if not self.pending_use:
            self.pending_material_requests = set()
        self.state = "POST_EVENT_REVIEW"
        self._validate_instance(sku)

    def update_instance(
        self,
        sku: str,
        *,
        quantity_available: int,
        lot: str,
        expiry_date: str | None,
        inserted_at: str,
        status: str,
    ) -> None:
        instance = self._instance(sku)
        if sku in self.pending_use:
            raise ValueError(f"Inventory Instance {sku} in uso pendente")
        if status == PENDING_USE:
            raise ValueError("PENDING_USE e' gestito automaticamente durante l'intervento")
        if status not in INVENTORY_STATUSES:
            raise ValueError(f"Stato inventario non valido: {status}")
        if quantity_available == 0 and status == AVAILABLE:
            status = MISSING
        if quantity_available > 0 and status in {USED, MISSING}:
            raise ValueError(f"Lo stato {status} richiede quantita' zero")
        instance.set_values(
            quantity_available=quantity_available,
            lot=lot,
            expiry_date=expiry_date,
            inserted_at=inserted_at,
            status=status,
            quantity_expected=self._quantity_expected(sku),
            tracks_expiry=self._tracks_expiry(sku),
        )
        self.suspected_missing.discard(sku)
        if instance.status == SUSPECTED_MISSING:
            instance.suspected_quantity = max(
                instance.suspected_quantity,
                int(self.catalog.items[sku]["quantity_expected"]),
            )
            self.suspected_missing.add(sku)
        self.local_dirty = True
        self.state = "SYNC_PENDING"
        self._validate_instance(sku)

    def discard_pending(self) -> None:
        for sku in self.pending_use:
            instance = self._instance(sku)
            instance.status = AVAILABLE if instance.quantity_available else USED
            instance.refresh_expiry(self._tracks_expiry(sku))
            instance.touch()
            self._validate_instance(sku)
        self.pending_use = {}
        self.pending_material_requests = set()
        self.review_candidates = set()
        self.correction_enabled = False
        self.state = "SYNC_PENDING" if self.local_dirty else "READY"
        self._validate_all()

    def finalize_pending(self) -> None:
        changed = bool(self.pending_use or self.suspected_missing)
        for sku, quantity in self.pending_use.items():
            instance = self._instance(sku)
            if quantity > instance.quantity_available:
                raise ValueError(f"Stock insufficiente durante la conferma: {sku}")
            instance.quantity_available -= quantity
            self.used[sku] = self.used.get(sku, 0) + quantity
            instance.status = AVAILABLE if instance.quantity_available else USED
            instance.refresh_expiry(self._tracks_expiry(sku))
            instance.touch()
            self._validate_instance(sku)

        for sku in self.suspected_missing:
            instance = self._instance(sku)
            instance.quantity_available = 0
            instance.suspected_quantity = 0
            instance.status = MISSING
            instance.touch()
            self._validate_instance(sku)

        self.pending_use = {}
        self.pending_material_requests = set()
        self.suspected_missing = set()
        self.review_candidates = set()
        self.correction_enabled = False
        self.local_dirty = self.local_dirty or changed
        self.state = "DIRTY" if self.local_dirty else "READY"
        self._validate_all()

    def mark_sync_pending(self) -> None:
        self.state = "SYNC_PENDING"

    def restore(self, snapshot: dict[str, Any]) -> None:
        expected = self.catalog.expected_stock()
        self.used = {
            str(sku): int(quantity)
            for sku, quantity in snapshot.get("used", {}).items()
            if sku in self.catalog.items and int(quantity) > 0
        }
        stored_instances = snapshot.get("instances", [])
        by_sku = {
            str(item.get("sku")): item
            for item in stored_instances
            if isinstance(item, dict) and item.get("sku") in self.catalog.items
        }
        stored_stock = snapshot.get("stock", {})
        self.instances = {}
        for sku, quantity_expected in expected.items():
            stored = by_sku.get(sku)
            if stored is None:
                quantity_available = int(stored_stock.get(sku, quantity_expected))
                status = AVAILABLE
                if quantity_available == 0:
                    status = USED if self.used.get(sku, 0) else MISSING
                stored = {
                    "quantity_available": quantity_available,
                    "status": status,
                }
            self.instances[sku] = InventoryInstance.restore(
                stored,
                sku,
                quantity_expected,
                self._tracks_expiry(sku),
            )
        self.pending_use = {
            str(sku): int(quantity)
            for sku, quantity in snapshot.get("pending_use", {}).items()
            if sku in self.catalog.items and int(quantity) > 0
        }
        self.pending_material_requests = set(
            snapshot.get("pending_material_requests", [])
        )
        self.suspected_missing = {
            sku
            for sku in snapshot.get("suspected_missing", [])
            if sku in self.catalog.items
        }
        self.suspected_missing.update(
            sku
            for sku, instance in self.instances.items()
            if instance.status == SUSPECTED_MISSING
        )
        self.review_candidates = {
            sku
            for sku in snapshot.get("review_candidates", [])
            if sku in self.catalog.items
        }
        self.correction_enabled = bool(snapshot.get("correction_enabled", False))
        for sku, instance in self.instances.items():
            if sku in self.pending_use:
                if self.pending_use[sku] > instance.quantity_available:
                    raise ValueError(f"Pending use fuori limite per {sku}")
                instance.status = PENDING_USE
            self._validate_instance(sku)
        self.local_dirty = bool(snapshot.get("local_dirty", False))
        self.state = str(snapshot.get("state", "READY"))
        self._validate_all()

    def restore_legacy(self, snapshot: dict[str, Any]) -> None:
        self.reset()
        for material_id, quantity in snapshot.get("used", {}).items():
            if material_id not in self.catalog.material_requests:
                continue
            sku = self.catalog.preferred_sku(material_id)
            migrated_quantity = max(0, int(quantity))
            if migrated_quantity:
                instance = self._instance(sku)
                actual = min(migrated_quantity, instance.quantity_available)
                self.used[sku] = self.used.get(sku, 0) + actual
                instance.quantity_available -= actual
                instance.status = AVAILABLE if instance.quantity_available else USED
                instance.touch()
                self._validate_instance(sku)
        self.local_dirty = bool(snapshot.get("local_dirty", False) or self.used)
        self.state = "SYNC_PENDING" if self.local_dirty else "READY"
        self._validate_all()

    def pending_items(self) -> list[dict[str, Any]]:
        return [
            {
                **self.catalog.item_summary(sku, quantity),
                "status": PENDING_USE,
                "review_kind": "USE",
            }
            for sku, quantity in self.pending_use.items()
        ]

    def review_items(self) -> list[dict[str, Any]]:
        items = []
        for sku in sorted(self.review_candidates):
            instance = self._instance(sku)
            suspected = sku in self.suspected_missing or instance.status == SUSPECTED_MISSING
            quantity = 0 if suspected else self.pending_use.get(sku, 0)
            maximum = (
                max(
                    instance.suspected_quantity,
                    int(self.catalog.items[sku]["quantity_expected"]),
                )
                if suspected
                else instance.quantity_available
            )
            items.append(
                {
                    **self.catalog.item_summary(sku, quantity),
                    "maximum": maximum,
                    "status": instance.status,
                    "review_kind": "MISSING" if suspected else "USE",
                }
            )
        return items

    def maintenance_snapshot(self) -> dict[str, Any]:
        item_rows = self._maintenance_items()
        zones = []
        for zone_id, zone in sorted(
            self.catalog.zones.items(),
            key=lambda entry: int(entry[1].get("priority", 0)),
        ):
            zone_items = [item for item in item_rows if item["zone"] == zone_id]
            zones.append(
                {
                    "zone": zone_id,
                    "name_it": zone["name_it"],
                    "led_id": zone["led_id"],
                    "status": self._aggregate_status(zone_items),
                    "quantity_expected": sum(item["quantity_expected"] for item in zone_items),
                    "quantity_available": sum(item["quantity_usable"] for item in zone_items),
                    "items": zone_items,
                }
            )
        return {
            "kit_status": self._aggregate_status(item_rows),
            "zones": zones,
            "instances": item_rows,
            "status_counts": {
                status: sum(1 for item in item_rows if item["status"] == status)
                for status in sorted(INVENTORY_STATUSES)
            },
            "expiry_counts": {
                status: sum(1 for item in item_rows if item["expiry_status"] == status)
                for status in (
                    "VALID",
                    "EXPIRING_SOON",
                    "EXPIRED",
                    "UNKNOWN",
                    "NOT_TRACKED",
                )
            },
        }

    def snapshot(self) -> dict[str, Any]:
        maintenance = self.maintenance_snapshot()
        return copy.deepcopy(
            {
                "state": self.state,
                "bom_version": self.catalog.version,
                "stock": self.stock,
                "instances": [
                    self.instances[sku].snapshot()
                    for sku in self.catalog.items
                ],
                "maintenance": maintenance,
                "kit_status": maintenance["kit_status"],
                "pending_use": self.pending_use,
                "pending_material_requests": sorted(self.pending_material_requests),
                "pending_items": self.pending_items(),
                "suspected_missing": sorted(self.suspected_missing),
                "review_candidates": sorted(self.review_candidates),
                "review_items": self.review_items(),
                "correction_enabled": self.correction_enabled,
                "used": self.used,
                "local_dirty": self.local_dirty,
                "finalized": (
                    not self.pending_use
                    and not self.suspected_missing
                    and self.local_dirty
                ),
            }
        )

    def _maintenance_items(self) -> list[dict[str, Any]]:
        rows = []
        today = date.today()
        for sku, item in self.catalog.items.items():
            instance = self._instance(sku)
            instance.refresh_expiry(
                bool(item.get("expiry_tracking", False)),
                today,
            )
            self._validate_instance(sku)
            expiry_status = instance.expiry_status(
                bool(item.get("expiry_tracking", False)),
                today,
            )
            quantity_usable = self.available_quantity(sku)
            rows.append(
                {
                    **self.catalog.item_summary(sku, instance.quantity_available),
                    "instance_id": instance.instance_id,
                    "quantity_expected": int(item["quantity_expected"]),
                    "quantity_available": instance.quantity_available,
                    "quantity_usable": quantity_usable,
                    "lot": instance.lot,
                    "expiry_date": instance.expiry_date,
                    "expiry_tracking": bool(item.get("expiry_tracking", False)),
                    "expiry_status": expiry_status,
                    "inserted_at": instance.inserted_at,
                    "updated_at": instance.updated_at,
                    "status": instance.status,
                    "criticality": str(item.get("criticality", "low")),
                    "health": self.readiness_policy.item_health(
                        status=instance.status,
                        expiry_status=expiry_status,
                        quantity_usable=quantity_usable,
                        quantity_expected=int(item["quantity_expected"]),
                        criticality=str(item.get("criticality", "low")),
                    ),
                }
            )
        return rows

    def _aggregate_status(self, items: list[dict[str, Any]]) -> str:
        return self.readiness_policy.aggregate(
            [str(item["health"]) for item in items]
        )

    def _quantity_expected(self, sku: str) -> int:
        return int(self.catalog.items[sku]["quantity_expected"])

    def _tracks_expiry(self, sku: str) -> bool:
        return bool(self.catalog.items[sku].get("expiry_tracking", False))

    def _validate_instance(self, sku: str) -> None:
        self._instance(sku).validate(self._quantity_expected(sku))

    def _validate_all(self) -> None:
        for sku in self.catalog.items:
            self._validate_instance(sku)
            status = self.instances[sku].status
            if (status == PENDING_USE) != (sku in self.pending_use):
                raise ValueError(f"Stato PENDING_USE incoerente per {sku}")
            if (status == SUSPECTED_MISSING) != (sku in self.suspected_missing):
                raise ValueError(f"Stato SUSPECTED_MISSING incoerente per {sku}")

    def _instance(self, sku: str) -> InventoryInstance:
        try:
            return self.instances[sku]
        except KeyError as exc:
            raise BOMError(f"SKU inventario sconosciuto: {sku}") from exc
