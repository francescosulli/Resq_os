from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any


AVAILABLE = "AVAILABLE"
PENDING_USE = "PENDING_USE"
SUSPECTED_MISSING = "SUSPECTED_MISSING"
USED = "USED"
MISSING = "MISSING"
EXPIRED = "EXPIRED"

INVENTORY_STATUSES = {
    AVAILABLE,
    PENDING_USE,
    SUSPECTED_MISSING,
    USED,
    MISSING,
    EXPIRED,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class InventoryInstance:
    """Mutable data for one physical SKU batch in a specific ResQ case."""

    instance_id: str
    sku: str
    quantity_available: int
    lot: str
    expiry_date: str | None
    inserted_at: str
    status: str
    updated_at: str
    suspected_quantity: int = 0

    @classmethod
    def create(cls, sku: str, quantity: int) -> InventoryInstance:
        now = utc_now()
        instance = cls(
            instance_id=f"RESQ-{sku}-01",
            sku=sku,
            quantity_available=max(0, int(quantity)),
            lot="",
            expiry_date=None,
            inserted_at=now,
            status=AVAILABLE if quantity > 0 else MISSING,
            updated_at=now,
        )
        instance.validate(quantity)
        return instance

    @classmethod
    def restore(
        cls,
        data: dict[str, Any],
        sku: str,
        default_quantity: int,
        tracks_expiry: bool,
    ) -> InventoryInstance:
        now = utc_now()
        status = str(data.get("status", AVAILABLE))
        if status not in INVENTORY_STATUSES:
            raise ValueError(f"Stato Inventory Instance non valido per {sku}: {status}")
        instance = cls(
            instance_id=str(data.get("instance_id", f"RESQ-{sku}-01")),
            sku=sku,
            quantity_available=int(data.get("quantity_available", default_quantity)),
            lot=str(data.get("lot") or ""),
            expiry_date=data.get("expiry_date") or None,
            inserted_at=str(data.get("inserted_at", now)),
            status=status,
            updated_at=str(data.get("updated_at", now)),
            suspected_quantity=int(data.get("suspected_quantity", 0)),
        )
        instance.refresh_expiry(tracks_expiry)
        instance.validate(default_quantity)
        return instance

    def expiry_status(self, tracks_expiry: bool, today: date | None = None) -> str:
        if not tracks_expiry:
            return "NOT_TRACKED"
        if self.status == EXPIRED:
            return "EXPIRED"
        if not self.expiry_date:
            return "UNKNOWN"
        expiry = _parse_date(self.expiry_date)
        current = today or date.today()
        days_remaining = (expiry - current).days
        if days_remaining < 0:
            return "EXPIRED"
        if days_remaining <= 30:
            return "EXPIRING_SOON"
        return "VALID"

    def refresh_expiry(
        self,
        tracks_expiry: bool,
        today: date | None = None,
    ) -> None:
        if (
            tracks_expiry
            and self.expiry_date
            and self.expiry_status(True, today) == "EXPIRED"
        ):
            if self.status == AVAILABLE:
                self.status = EXPIRED

    def set_values(
        self,
        *,
        quantity_available: int,
        lot: str,
        expiry_date: str | None,
        inserted_at: str,
        status: str,
        quantity_expected: int,
        tracks_expiry: bool,
    ) -> None:
        if status not in INVENTORY_STATUSES:
            raise ValueError(f"Stato inventario non valido: {status}")
        if quantity_available < 0:
            raise ValueError("La quantita' disponibile non puo' essere negativa")
        if expiry_date:
            _parse_date(expiry_date)
        _parse_datetime(inserted_at)
        candidate = copy.deepcopy(self)
        candidate.quantity_available = int(quantity_available)
        candidate.lot = lot.strip()
        candidate.expiry_date = expiry_date or None
        candidate.inserted_at = inserted_at
        candidate.status = status
        candidate.suspected_quantity = 0
        candidate.touch()
        candidate.refresh_expiry(tracks_expiry)
        candidate.validate(quantity_expected)
        self.__dict__.update(candidate.__dict__)

    def validate(self, quantity_expected: int) -> None:
        if quantity_expected < 0:
            raise ValueError(f"Quantita' BOM non valida per {self.sku}")
        if not 0 <= self.quantity_available <= quantity_expected:
            raise ValueError(
                f"Quantita' Inventory Instance fuori limite per {self.sku}: "
                f"{self.quantity_available}/{quantity_expected}"
            )
        if not 0 <= self.suspected_quantity <= quantity_expected:
            raise ValueError(f"Quantita' sospetta fuori limite per {self.sku}")
        if self.status in {USED, MISSING, SUSPECTED_MISSING}:
            if self.quantity_available != 0:
                raise ValueError(
                    f"Lo stato {self.status} richiede quantita' zero per {self.sku}"
                )
        if self.status in {AVAILABLE, PENDING_USE} and self.quantity_available == 0:
            raise ValueError(
                f"Lo stato {self.status} richiede quantita' positiva per {self.sku}"
            )

    def touch(self) -> None:
        self.updated_at = utc_now()

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "instance_id": self.instance_id,
                "sku": self.sku,
                "quantity_available": self.quantity_available,
                "lot": self.lot,
                "expiry_date": self.expiry_date,
                "inserted_at": self.inserted_at,
                "status": self.status,
                "updated_at": self.updated_at,
                "suspected_quantity": self.suspected_quantity,
            }
        )


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Data di scadenza non valida") from exc


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Data di inserimento non valida") from exc
