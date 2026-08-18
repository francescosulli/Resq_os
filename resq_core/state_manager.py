from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


EVENT_COMMIT_KEY = "_event_commit"


class StatePersistenceError(RuntimeError):
    """Raised when a persisted ResQ session cannot be loaded or stored."""


class StateManager:
    def __init__(
        self,
        initial_state: dict[str, Any],
        state_path: str | Path | None = None,
        event_log_path: str | Path | None = None,
    ) -> None:
        self._lock = RLock()
        self.state_path = Path(state_path) if state_path else None
        self.event_log_path = Path(event_log_path) if event_log_path else None
        self.loaded_from_disk = False
        self._state = copy.deepcopy(initial_state)
        self._load_if_available()

    def save(
        self,
        state: dict[str, Any],
        event_record: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            candidate = copy.deepcopy(state)
            committed_event = None
            if event_record is not None:
                committed_event = copy.deepcopy(event_record)
                committed_event.setdefault("event_id", str(uuid4()))
                candidate[EVENT_COMMIT_KEY] = committed_event
            elif EVENT_COMMIT_KEY in self._state:
                candidate[EVENT_COMMIT_KEY] = copy.deepcopy(
                    self._state[EVENT_COMMIT_KEY]
                )
            self._write_state(candidate)
            self._state = candidate
            if committed_event is not None:
                self._ensure_event_logged(committed_event)
            return copy.deepcopy(self._state)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

    def _load_if_available(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            with self.state_path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise StatePersistenceError(
                f"Impossibile caricare lo stato persistito: {self.state_path}"
            ) from exc
        if not isinstance(loaded, dict) or "state_id" not in loaded:
            raise StatePersistenceError("Formato dello stato persistito non valido")
        self._state = loaded
        self.loaded_from_disk = True
        committed_event = loaded.get(EVENT_COMMIT_KEY)
        if committed_event is not None:
            if not isinstance(committed_event, dict) or not committed_event.get(
                "event_id"
            ):
                raise StatePersistenceError("Commit evento persistito non valido")
            self._ensure_event_logged(committed_event)

    def _write_state(self, state: dict[str, Any]) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.state_path)
            self._fsync_directory(self.state_path.parent)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise StatePersistenceError(
                f"Impossibile salvare lo stato: {self.state_path}"
            ) from exc

    def _ensure_event_logged(self, event_record: dict[str, Any]) -> None:
        if self.event_log_path is None:
            return
        records = self._read_event_records()
        event_id = str(event_record["event_id"])
        if any(str(record.get("event_id")) == event_id for record in records):
            return
        records.append(copy.deepcopy(event_record))
        self._write_event_records(records)

    def _read_event_records(self) -> list[dict[str, Any]]:
        if self.event_log_path is None or not self.event_log_path.exists():
            return []
        try:
            lines = self.event_log_path.read_text(encoding="utf-8").splitlines()
            records = [json.loads(line) for line in lines if line.strip()]
        except (OSError, json.JSONDecodeError) as exc:
            raise StatePersistenceError(
                f"Impossibile leggere il session log: {self.event_log_path}"
            ) from exc
        if not all(isinstance(record, dict) for record in records):
            raise StatePersistenceError("Formato del session log non valido")
        return records

    def _write_event_records(self, records: list[dict[str, Any]]) -> None:
        if self.event_log_path is None:
            return
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.event_log_path.with_suffix(
            self.event_log_path.suffix + ".tmp"
        )
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.event_log_path)
            self._fsync_directory(self.event_log_path.parent)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise StatePersistenceError(
                f"Impossibile aggiornare il session log: {self.event_log_path}"
            ) from exc

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
