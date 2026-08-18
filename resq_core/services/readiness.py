from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReadinessPolicy:
    """Maps physical inventory health to one release-level readiness status."""

    critical_shortage_status: str = "NON_OPERATIONAL"
    unavailable_status: str = "REFILL_REQUIRED"
    shortage_status: str = "REFILL_REQUIRED"
    unknown_expiry_status: str = "MAINTENANCE"
    expiring_soon_status: str = "MAINTENANCE"
    priorities: dict[str, int] = field(
        default_factory=lambda: {
            "READY": 0,
            "MAINTENANCE": 1,
            "REFILL_REQUIRED": 2,
            "NON_OPERATIONAL": 3,
        }
    )

    def item_health(
        self,
        *,
        status: str,
        expiry_status: str,
        quantity_usable: int,
        quantity_expected: int,
        criticality: str,
    ) -> str:
        unavailable = status in {
            "SUSPECTED_MISSING",
            "MISSING",
            "USED",
            "EXPIRED",
        }
        shortage = quantity_usable < quantity_expected
        if criticality == "critical" and (unavailable or shortage):
            return self.critical_shortage_status
        if unavailable:
            return self.unavailable_status
        if shortage or expiry_status == "EXPIRED":
            return self.shortage_status
        if expiry_status == "UNKNOWN":
            return self.unknown_expiry_status
        if expiry_status == "EXPIRING_SOON":
            return self.expiring_soon_status
        return "READY"

    def aggregate(self, statuses: list[str]) -> str:
        if not statuses:
            return "READY"
        unknown = set(statuses).difference(self.priorities)
        if unknown:
            raise ValueError(f"Stati readiness sconosciuti: {sorted(unknown)}")
        return max(statuses, key=lambda status: self.priorities[status])


DEFAULT_READINESS_POLICY = ReadinessPolicy()
