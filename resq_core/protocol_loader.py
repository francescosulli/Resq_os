from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ProtocolError(ValueError):
    """Raised when a protocol file is invalid."""


class ProtocolLoader:
    def __init__(self, protocols_dir: str | Path) -> None:
        self.protocols_dir = Path(protocols_dir)

    def load_all(self) -> dict[str, dict[str, Any]]:
        protocols: dict[str, dict[str, Any]] = {}
        for path in sorted(self.protocols_dir.glob("*.json")):
            protocol = self._load_file(path)
            protocol_id = protocol["id"]
            if protocol_id in protocols:
                raise ProtocolError(f"Protocollo duplicato: {protocol_id}")
            protocols[protocol_id] = protocol

        if not protocols:
            raise ProtocolError(f"Nessun protocollo trovato in {self.protocols_dir}")

        return protocols

    def list_summaries(self, protocols: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
        return [
            {
                "id": protocol["id"],
                "title": protocol["title"],
                "disclaimer": protocol.get("disclaimer", ""),
            }
            for protocol in sorted(
                protocols.values(),
                key=lambda item: (item.get("order", 999), item["title"]),
            )
        ]

    def _load_file(self, path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"JSON non valido in {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ProtocolError(f"Protocollo non valido in {path}: root non oggetto")

        self._validate_protocol(data, path)
        return data

    def _validate_protocol(self, protocol: dict[str, Any], path: Path) -> None:
        for key in ("id", "title", "first_step", "steps"):
            if key not in protocol:
                raise ProtocolError(f"{path}: manca il campo '{key}'")

        if not isinstance(protocol["steps"], list) or not protocol["steps"]:
            raise ProtocolError(f"{path}: 'steps' deve essere una lista non vuota")

        step_ids: set[str] = set()
        for step in protocol["steps"]:
            if not isinstance(step, dict):
                raise ProtocolError(f"{path}: ogni step deve essere un oggetto")
            for key in ("id", "type", "instruction"):
                if key not in step:
                    raise ProtocolError(f"{path}: step senza campo '{key}'")
            if step["id"] in step_ids:
                raise ProtocolError(f"{path}: step duplicato '{step['id']}'")
            step_ids.add(step["id"])

            step_type = step["type"]
            if step_type == "question":
                answers = step.get("answers")
                if not isinstance(answers, dict) or "yes" not in answers or "no" not in answers:
                    raise ProtocolError(f"{path}: question '{step['id']}' senza yes/no")
            elif step_type == "item":
                item = step.get("item")
                if not isinstance(item, dict):
                    raise ProtocolError(f"{path}: item '{step['id']}' senza item")
                for key in ("name", "compartment", "nfc_tag"):
                    if key not in item:
                        raise ProtocolError(f"{path}: item '{step['id']}' senza '{key}'")
            elif step_type not in {"instruction", "end"}:
                raise ProtocolError(f"{path}: tipo step non supportato '{step_type}'")

        if protocol["first_step"] not in step_ids:
            raise ProtocolError(f"{path}: first_step non trovato")

        for step in protocol["steps"]:
            references = []
            if "next" in step:
                references.append(step["next"])
            if step["type"] == "question":
                references.extend(step["answers"].values())
            for target in references:
                if target not in step_ids:
                    raise ProtocolError(
                        f"{path}: step '{step['id']}' punta a '{target}' inesistente"
                    )
