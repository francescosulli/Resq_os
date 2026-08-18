from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class AppSyncService:
    """Offline-first queue boundary; transport to ResQ Connect is intentionally absent."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state = "DISCONNECTED"
        self.queue_state: str | None = None
        self.pending_payload: dict[str, Any] | None = None
        self.last_error: str | None = None

    def queue_sync(self, payload: dict[str, Any]) -> str:
        idempotency_key = self._idempotency_key(payload)
        if (
            self.pending_payload
            and self.pending_payload.get("idempotency_key") == idempotency_key
        ):
            self.queue_state = "SYNC_PENDING"
            return idempotency_key
        self.pending_payload = {
            "schema_version": 2,
            "idempotency_key": idempotency_key,
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "inventory": copy.deepcopy(payload),
        }
        self.queue_state = "SYNC_PENDING"
        return idempotency_key

    def mark_synced(self, idempotency_key: str | None = None) -> bool:
        if (
            idempotency_key
            and self.pending_payload
            and self.pending_payload.get("idempotency_key") != idempotency_key
        ):
            return False
        self.pending_payload = None
        self.queue_state = None
        self.state = "CONNECTED"
        self.last_error = None
        return True

    def restore(self, snapshot: dict[str, Any]) -> None:
        self.state = str(snapshot.get("state", "DISCONNECTED"))
        self.queue_state = snapshot.get("queue_state")
        stored_payload = copy.deepcopy(snapshot.get("pending_payload"))
        if stored_payload:
            inventory = stored_payload.get("inventory", stored_payload)
            queued_at = stored_payload.get("queued_at")
            self.pending_payload = {
                "schema_version": 2,
                "idempotency_key": stored_payload.get("idempotency_key")
                or self._idempotency_key(inventory),
                "queued_at": queued_at
                or datetime.now(timezone.utc).isoformat(),
                "inventory": inventory,
            }
            self.queue_state = "SYNC_PENDING"
        else:
            self.pending_payload = None
        self.last_error = snapshot.get("last_error")

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "state": self.state,
                "queue_state": self.queue_state,
                "pending_payload": self.pending_payload,
                "last_error": self.last_error,
                "blocks_emergency": False,
            }
        )

    @staticmethod
    def _idempotency_key(payload: dict[str, Any]) -> str:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"inventory-sha256:{hashlib.sha256(canonical).hexdigest()}"
