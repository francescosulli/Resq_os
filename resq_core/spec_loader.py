from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class SpecError(ValueError):
    """Raised when the handoff source files are internally inconsistent."""


@dataclass(frozen=True)
class HandoffSpec:
    flow: dict[str, Any]
    architecture: dict[str, Any]
    bom: dict[str, Any]

    @property
    def version(self) -> str:
        return str(self.flow["version"])

    @property
    def states(self) -> dict[str, dict[str, Any]]:
        return self.flow["states"]

    @property
    def materials(self) -> dict[str, dict[str, Any]]:
        """Semantic MaterialRequest declarations from the clinical flow."""
        return self.flow["materials"]

    @property
    def material_requests(self) -> dict[str, dict[str, Any]]:
        return self.bom["material_requests"]

    @property
    def items(self) -> dict[str, dict[str, Any]]:
        return self.bom["items"]

    @property
    def zones(self) -> dict[str, dict[str, Any]]:
        return self.bom["zones"]

    @property
    def events(self) -> set[str]:
        return set(self.architecture["events"])


class HandoffSpecLoader:
    def __init__(
        self,
        flow_path: str | Path,
        architecture_path: str | Path,
        bom_path: str | Path,
    ) -> None:
        self.flow_path = Path(flow_path)
        self.architecture_path = Path(architecture_path)
        self.bom_path = Path(bom_path)

    def load(self) -> HandoffSpec:
        with self.flow_path.open("r", encoding="utf-8") as handle:
            flow = json.load(handle)
        with self.architecture_path.open("r", encoding="utf-8") as handle:
            architecture = yaml.safe_load(handle)
        with self.bom_path.open("r", encoding="utf-8") as handle:
            bom = yaml.safe_load(handle)

        if not all(isinstance(source, dict) for source in (flow, architecture, bom)):
            raise SpecError("Le specifiche devono avere una root a oggetto")

        spec = HandoffSpec(flow=flow, architecture=architecture, bom=bom)
        self._validate(spec)
        return spec

    def _validate(self, spec: HandoffSpec) -> None:
        if spec.version != "1.2":
            raise SpecError(f"Versione handoff non supportata: {spec.version}")
        if str(spec.architecture.get("version")) != "1.2":
            raise SpecError("La State Machine deve essere in versione 1.2")
        if str(spec.bom.get("bom_version")) != "1.0":
            raise SpecError("La Automotive BOM deve restare in versione 1.0")
        if spec.flow.get("status") != (
            "prototype_clinical_flow_v1_2_not_clinically_certified"
        ):
            raise SpecError("Stato di validazione clinica v1.2 inatteso")
        if spec.flow.get("kit_policy", {}).get("medicines_in_kit") is not False:
            raise SpecError("La specifica non deve prevedere medicinali nel kit")
        if spec.bom.get("design_principles", {}).get("no_medicines") is not True:
            raise SpecError("La BOM deve vietare i medicinali")

        self._validate_bom(spec)
        self._validate_states(spec)
        self._validate_services(spec)

        reachable = self._reachable_states(spec.states)
        unreachable = {
            state_id
            for state_id in set(spec.states) - reachable
            if not spec.states[state_id].get("compatibility_only")
        }
        if unreachable:
            raise SpecError("Stati non raggiungibili: " + ", ".join(sorted(unreachable)))

    def _validate_states(self, spec: HandoffSpec) -> None:
        states = spec.states
        if "EM_START" not in states:
            raise SpecError("Stato iniziale EM_START mancante")

        max_keys = int(spec.flow.get("ui_rules", {}).get("max_soft_keys", 3))
        for state_id, node in states.items():
            for key in ("label", "type", "prompt", "buttons"):
                if key not in node:
                    raise SpecError(f"{state_id}: campo '{key}' mancante")

            buttons = node["buttons"]
            if not isinstance(buttons, list) or len(buttons) != max_keys:
                raise SpecError(
                    f"{state_id}: devono essere definite esattamente {max_keys} soft-key"
                )
            if not all(isinstance(label, str) for label in buttons):
                raise SpecError(f"{state_id}: le soft-key devono essere stringhe")

            transitions = node.get("next", {})
            if not isinstance(transitions, dict):
                raise SpecError(f"{state_id}: 'next' deve essere un oggetto")
            for button_label, target in transitions.items():
                if button_label not in buttons:
                    raise SpecError(
                        f"{state_id}: transizione '{button_label}' non presente nei pulsanti"
                    )
                if target != "IDLE" and target not in states:
                    raise SpecError(f"{state_id}: target inesistente '{target}'")

            parallel_events = node.get("parallel_events", {})
            if not isinstance(parallel_events, dict):
                raise SpecError(f"{state_id}: 'parallel_events' deve essere un oggetto")
            for event, target in parallel_events.items():
                if event not in spec.events:
                    raise SpecError(f"{state_id}: evento parallelo sconosciuto '{event}'")
                if target not in states:
                    raise SpecError(f"{state_id}: target parallelo inesistente '{target}'")

            material_ids = node.get("materials", [])
            if not isinstance(material_ids, list) or len(material_ids) > 1:
                raise SpecError(f"{state_id}: e' ammessa una sola MaterialRequest")
            for material_id in material_ids:
                if material_id not in spec.material_requests:
                    raise SpecError(
                        f"{state_id}: MaterialRequest BOM sconosciuta '{material_id}'"
                    )

            led_zone = node.get("led_zone")
            if led_zone is not None and led_zone not in spec.zones:
                raise SpecError(f"{state_id}: zona LED BOM sconosciuta '{led_zone}'")
            if bool(material_ids) != bool(led_zone):
                raise SpecError(
                    f"{state_id}: MaterialRequest e singola zona LED devono coesistere"
                )
            if material_ids:
                request_zones = self._request_zones(spec, material_ids[0])
                if led_zone not in request_zones:
                    raise SpecError(
                        f"{state_id}: la zona clinica non e' prevista dalla BOM "
                        f"per {material_ids[0]}"
                    )

            forbidden_keys = {"sku", "slot", "led_id"} & set(node)
            if forbidden_keys:
                raise SpecError(
                    f"{state_id}: riferimenti fisici vietati nel flow: "
                    + ", ".join(sorted(forbidden_keys))
                )

            if node["type"] == "decision" and "NON SO" in buttons:
                if "NON SO" not in transitions:
                    raise SpecError(f"{state_id}: ramo prudenziale NON SO mancante")

        guidance = states.get("AED_USE", {}).get("aed_guidance_by_age_class", {})
        if set(guidance) != {"UNKNOWN", "INFANT", "CHILD", "ADULT"}:
            raise SpecError("AED_USE: guida age_class incompleta")
        for age_class, content in guidance.items():
            required = {"lead", "mode", "fallback"}
            if not isinstance(content, dict) or not required.issubset(content):
                raise SpecError(f"AED_USE/{age_class}: guida DAE incompleta")
            if not all(str(content[key]).strip() for key in required):
                raise SpecError(f"AED_USE/{age_class}: guida DAE vuota")

    def _validate_bom(self, spec: HandoffSpec) -> None:
        if set(spec.materials) != set(spec.material_requests):
            mismatch = set(spec.materials) ^ set(spec.material_requests)
            raise SpecError(
                "Catalogo MaterialRequest flow/BOM non coerente: "
                + ", ".join(sorted(mismatch))
            )

        led_ids: set[str] = set()
        for zone_id, zone in spec.zones.items():
            led_id = zone.get("led_id")
            if not zone.get("name_it") or not led_id:
                raise SpecError(f"Zona BOM incompleta: {zone_id}")
            if led_id in led_ids:
                raise SpecError(f"LED BOM duplicato: {led_id}")
            led_ids.add(str(led_id))

        slots: set[str] = set()
        for sku, item in spec.items.items():
            zone_id = item.get("zone")
            slot = item.get("slot")
            quantity = item.get("quantity_expected")
            if zone_id not in spec.zones:
                raise SpecError(f"{sku}: zona BOM inesistente '{zone_id}'")
            if not isinstance(slot, str) or not slot:
                raise SpecError(f"{sku}: slot BOM mancante")
            if slot in slots:
                raise SpecError(f"Slot BOM duplicato: {slot}")
            slots.add(slot)
            if not isinstance(quantity, int) or quantity < 1:
                raise SpecError(f"{sku}: quantita' BOM non valida")
            if not item.get("name_it"):
                raise SpecError(f"{sku}: nome italiano BOM mancante")

        for request_id, request in spec.material_requests.items():
            candidates = list(request.get("preferred", [])) + list(
                request.get("fallback", [])
            )
            if not candidates:
                raise SpecError(f"{request_id}: nessuno SKU candidato")
            if len(candidates) != len(set(candidates)):
                raise SpecError(f"{request_id}: SKU candidati duplicati")
            unknown = set(candidates) - set(spec.items)
            if unknown:
                raise SpecError(
                    f"{request_id}: SKU BOM sconosciuti: "
                    + ", ".join(sorted(unknown))
                )
            flow_declaration = spec.materials[request_id]
            if flow_declaration.get("resolution_source") != self.bom_path.name:
                raise SpecError(
                    f"{request_id}: resolution_source non punta alla BOM v1.0"
                )
            if flow_declaration.get("zone_hint") not in self._request_zones(
                spec, request_id
            ):
                raise SpecError(f"{request_id}: zone_hint non coerente con la BOM")

    def _validate_services(self, spec: HandoffSpec) -> None:
        required_services = {
            "Call112Service",
            "MaterialService",
            "UIAudioService",
            "InventoryService",
            "AppSyncService",
        }
        services = spec.architecture.get("orthogonal_services", {})
        missing_services = required_services - set(services)
        if missing_services:
            raise SpecError(
                "Servizi State Machine 1.2 mancanti: "
                + ", ".join(sorted(missing_services))
            )

        material_source = services["MaterialService"].get("source_of_truth")
        inventory_source = services["InventoryService"].get("source_of_truth")
        if material_source != self.bom_path.name or inventory_source != self.bom_path.name:
            raise SpecError("MaterialService e InventoryService devono usare la BOM v1.0")

        required_events = {
            "EV_AED_AVAILABLE",
            "EV_ITEM_TAKEN",
            "EV_MATERIAL_NOT_FOUND",
            "EV_MATERIAL_UNAVAILABLE",
            "EV_SKIP",
        }
        missing_events = required_events - spec.events
        if missing_events:
            raise SpecError(
                "Eventi State Machine 1.2 mancanti: "
                + ", ".join(sorted(missing_events))
            )

        aed_contract = spec.architecture.get("event_contracts", {}).get(
            "EV_AED_AVAILABLE",
            {},
        )
        allowed_states = set(aed_contract.get("allowed_states", []))
        actual_states = {
            state_id
            for state_id, node in spec.states.items()
            if "EV_AED_AVAILABLE" in node.get("parallel_events", {})
        }
        if allowed_states != actual_states or aed_contract.get("target") != "AED_USE":
            raise SpecError("Contratto EV_AED_AVAILABLE non coerente con il Flow 1.2")
        if aed_contract.get("return_state_context") != "aed_return_state":
            raise SpecError("Contratto DAE privo di aed_return_state")
        expected_returns = {
            "ADULT_CPR": "ADULT_CPR_LOOP",
            "ADULT_CPR_LOOP": "ADULT_CPR_LOOP",
            "PED_CPR": "PED_CPR",
            "PED_CPR_COMP_ONLY": "PED_CPR_COMP_ONLY",
        }
        if aed_contract.get("return_state_by_source") != expected_returns:
            raise SpecError("Mappa di ritorno DAE non valida")
        if aed_contract.get("default_return_state") != "ADULT_CPR_LOOP":
            raise SpecError("Fallback di ritorno DAE non valido")
        if spec.architecture.get("context", {}).get("aed_return_state") != (
            "optional_state_id"
        ):
            raise SpecError("Context aed_return_state non dichiarato")

    @staticmethod
    def _request_zones(spec: HandoffSpec, request_id: str) -> set[str]:
        request = spec.material_requests[request_id]
        candidates = list(request.get("preferred", [])) + list(
            request.get("fallback", [])
        )
        return {str(spec.items[sku]["zone"]) for sku in candidates}

    @staticmethod
    def _reachable_states(states: dict[str, dict[str, Any]]) -> set[str]:
        pending = ["EM_START"]
        visited: set[str] = set()
        while pending:
            state_id = pending.pop()
            if state_id in visited:
                continue
            visited.add(state_id)
            for target in states[state_id].get("next", {}).values():
                if target in states and target not in visited:
                    pending.append(target)
            for target in states[state_id].get("parallel_events", {}).values():
                if target in states and target not in visited:
                    pending.append(target)
        return visited
