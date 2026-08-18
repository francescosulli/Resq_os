from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from resq_core.app import create_runtime
from resq_core.clinical_state_machine import ClinicalStateMachine
from resq_core.events import (
    EV_CALL112_STARTED,
    EV_CLOSE_SESSION,
    EV_DONE,
    EV_HANDOVER,
    EV_MATERIAL_NOT_FOUND,
    EV_MATERIAL_TAKEN,
    EV_NO,
    EV_OPERATOR_ACTIVE,
    EV_OPERATOR_ENDED,
    EV_PROBLEM,
    EV_RESPONSIVE,
    EV_SKIP,
    EV_STABLE,
    EV_START_EMERGENCY,
    EV_WORSENING,
    EV_YES,
    event_for_button,
)
from resq_core.services.call112 import Call112Service


ROOT = Path(__file__).resolve().parents[1]


class ReleaseV10Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary_directory.name)
        self.flow, _, self.spec = create_runtime(ROOT, self.data_dir)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def dispatch_many(flow, *events: str) -> dict:
        state = flow.public_state()
        for event in events:
            state = flow.dispatch_event(event)
        return state

    def enter_flow(self, flow=None) -> dict:
        active_flow = flow or self.flow
        active_flow.start_emergency()
        return active_flow.dispatch_event(EV_START_EMERGENCY)

    def enter_major_bleed(self, flow=None) -> dict:
        active_flow = flow or self.flow
        self.enter_flow(active_flow)
        return self.dispatch_many(active_flow, EV_YES, EV_NO, EV_YES)

    def enter_exposure(self, flow=None) -> dict:
        active_flow = flow or self.flow
        self.enter_flow(active_flow)
        return self.dispatch_many(
            active_flow,
            EV_YES,
            EV_NO,
            EV_NO,
            EV_RESPONSIVE,
            EV_YES,
            EV_NO,
            "EV_SELECT_NESSUNA",
            EV_NO,
        )

    def enter_wound_ppe(self, flow=None) -> dict:
        active_flow = flow or self.flow
        self.enter_exposure(active_flow)
        return self.dispatch_many(
            active_flow,
            "EV_SELECT_TRAUMA",
            "EV_SELECT_FERITA",
        )

    def enter_burn_cover(self, flow=None) -> dict:
        active_flow = flow or self.flow
        self.enter_exposure(active_flow)
        return self.dispatch_many(
            active_flow,
            "EV_SELECT_USTIONE_AMBIENTE",
            "EV_SELECT_USTIONE",
            EV_DONE,
        )

    def reach_post_event_from_bleed_controlled(self, flow=None) -> dict:
        active_flow = flow or self.flow
        return self.dispatch_many(
            active_flow,
            EV_YES,
            EV_RESPONSIVE,
            EV_YES,
            EV_YES,
            EV_DONE,
            EV_STABLE,
            EV_HANDOVER,
        )

    def test_inventory_instances_expiry_and_kit_status(self) -> None:
        inserted_at = datetime.now(timezone.utc).isoformat()
        for sku, item in self.spec.items.items():
            self.flow.inventory.update_instance(
                sku,
                quantity_available=int(item["quantity_expected"]),
                lot=f"LOT-{sku}",
                expiry_date="2099-12-31" if item["expiry_tracking"] else None,
                inserted_at=inserted_at,
                status="AVAILABLE",
            )

        maintenance = self.flow.inventory.maintenance_snapshot()
        self.assertEqual(maintenance["kit_status"], "READY")
        self.assertEqual(len(maintenance["zones"]), 5)
        self.assertTrue(all(zone["status"] == "READY" for zone in maintenance["zones"]))

        self.flow.inventory.update_instance(
            "DRESSING_K",
            quantity_available=1,
            lot="EXPIRED-LOT",
            expiry_date="2000-01-01",
            inserted_at=inserted_at,
            status="AVAILABLE",
        )
        maintenance = self.flow.inventory.maintenance_snapshot()
        expired = next(item for item in maintenance["instances"] if item["sku"] == "DRESSING_K")
        self.assertEqual(expired["status"], "EXPIRED")
        self.assertEqual(expired["expiry_status"], "EXPIRED")
        self.assertEqual(maintenance["kit_status"], "REFILL_REQUIRED")

        self.flow.inventory.update_instance(
            "TOURNIQUET_COMMERCIAL",
            quantity_available=0,
            lot="",
            expiry_date=None,
            inserted_at=inserted_at,
            status="MISSING",
        )
        self.assertEqual(
            self.flow.inventory.maintenance_snapshot()["kit_status"],
            "NON_OPERATIONAL",
        )

    def test_gloves_are_consumed_as_one_pair(self) -> None:
        state = self.enter_wound_ppe()
        resolved = state["services"]["materials"]["active_request"]["resolved"]
        self.assertEqual(resolved["sku"], "GLOVES_NITRILE")
        self.assertEqual(resolved["quantity"], 2)

        self.flow.dispatch_event(EV_MATERIAL_TAKEN)
        self.flow.dispatch_event(EV_MATERIAL_TAKEN)
        self.dispatch_many(self.flow, EV_STABLE, EV_HANDOVER)
        state = self.flow.dispatch_event(EV_CLOSE_SESSION)

        self.assertEqual(state["state_id"], "SESSION_END")
        self.assertEqual(state["services"]["inventory"]["stock"]["GLOVES_NITRILE"], 6)
        self.assertEqual(state["services"]["inventory"]["used"]["GLOVES_NITRILE"], 2)

    def test_not_found_marks_instance_suspected_then_uses_bom_fallback(self) -> None:
        state = self.enter_major_bleed()
        self.assertEqual(
            state["services"]["materials"]["active_request"]["resolved"]["sku"],
            "DRESSING_G",
        )

        state = self.flow.dispatch_event(EV_MATERIAL_NOT_FOUND)
        self.assertEqual(state["state_id"], "BLEED_DIRECT_PRESSURE")
        self.assertEqual(
            state["services"]["materials"]["active_request"]["resolved"]["sku"],
            "DRESSING_M_C1",
        )
        inventory = state["services"]["inventory"]
        self.assertIn("DRESSING_G", inventory["suspected_missing"])
        self.assertEqual(inventory["stock"]["DRESSING_G"], 0)
        suspected = next(
            item
            for item in inventory["maintenance"]["instances"]
            if item["sku"] == "DRESSING_G"
        )
        self.assertEqual(suspected["status"], "SUSPECTED_MISSING")
        self.assertNotEqual(suspected["quantity_usable"], suspected["quantity_expected"])

        self.flow.dispatch_event(EV_MATERIAL_TAKEN)
        state = self.reach_post_event_from_bleed_controlled()
        self.assertEqual(state["state_id"], "POST_EVENT_INVENTORY")
        self.assertTrue(
            any(item["review_kind"] == "MISSING" for item in state["services"]["inventory"]["review_items"])
        )

        self.flow.dispatch_event(EV_PROBLEM)
        state = self.flow.correct_inventory("DRESSING_G", 1)
        corrected = next(
            item
            for item in state["services"]["inventory"]["maintenance"]["instances"]
            if item["sku"] == "DRESSING_G"
        )
        self.assertEqual(corrected["status"], "AVAILABLE")
        self.assertEqual(corrected["quantity_available"], 1)

    def test_optional_skip_and_not_found_have_distinct_service_effects(self) -> None:
        state = self.enter_burn_cover()
        self.assertEqual(state["state_id"], "BURN_COVER")
        self.assertEqual(
            [key["label"] for key in state["soft_keys"]],
            ["NON TROVO", "SALTA", "FATTO"],
        )
        preferred_sku = state["services"]["materials"]["active_request"]["resolved"]["sku"]

        state = self.flow.dispatch_event(EV_MATERIAL_NOT_FOUND)
        self.assertEqual(state["state_id"], "BURN_COVER")
        self.assertIn(preferred_sku, state["services"]["inventory"]["suspected_missing"])
        fallback_sku = state["services"]["materials"]["active_request"]["resolved"]["sku"]
        self.assertNotEqual(fallback_sku, preferred_sku)

        state = self.flow.dispatch_event(EV_SKIP)
        self.assertEqual(state["state_id"], "MONITOR")
        self.assertNotIn(fallback_sku, state["services"]["inventory"]["suspected_missing"])
        self.dispatch_many(self.flow, EV_STABLE, EV_HANDOVER)
        state = self.flow.dispatch_event(EV_CLOSE_SESSION)
        confirmed_missing = next(
            item
            for item in state["services"]["inventory"]["instances"]
            if item["sku"] == preferred_sku
        )
        self.assertEqual(confirmed_missing["status"], "MISSING")

        with tempfile.TemporaryDirectory() as directory:
            other_flow, _, _ = create_runtime(ROOT, Path(directory))
            state = self.enter_burn_cover(other_flow)
            skipped_sku = state["services"]["materials"]["active_request"]["resolved"]["sku"]
            state = other_flow.dispatch_event(EV_SKIP)
            self.assertEqual(state["state_id"], "MONITOR")
            self.assertNotIn(skipped_sku, state["services"]["inventory"]["suspected_missing"])

    def test_all_call112_policies_and_return_to_flow(self) -> None:
        service = Call112Service()
        self.assertEqual(service.snapshot()["state"], "IDLE")

        service.apply_policy("CONDITIONAL")
        self.assertEqual(service.state, "CONDITIONAL")
        self.assertFalse(service.indicated)
        service.apply_policy(None)
        self.assertEqual(service.state, "RETURN_TO_FLOW")
        service.apply_policy(None)
        self.assertEqual(service.state, "IDLE")

        for policy in (
            "RECOMMENDED",
            "RECOMMENDED_IMMEDIATE",
            "REQUIRED_PROMPT",
            "OPERATOR_PRIORITY",
        ):
            service.reset()
            service.apply_policy(policy)
            self.assertEqual(service.state, policy)
            self.assertTrue(service.indicated)
        self.assertTrue(service.operator_priority)

        service.handle_event(EV_CALL112_STARTED)
        self.assertEqual(service.state, "USER_CALLING")
        self.assertFalse(service.operator_priority)
        service.handle_event(EV_OPERATOR_ACTIVE)
        self.assertTrue(service.operator_active)
        self.assertEqual(service.state, "OPERATOR_PRIORITY")
        service.handle_event(EV_OPERATOR_ENDED)
        self.assertEqual(service.state, "RETURN_TO_FLOW")
        self.assertFalse(service.operator_priority)

    def test_conditional_112_escalates_only_on_the_flow_condition(self) -> None:
        self.flow.engine.restore("CHOKE_ADULT", {})
        self.flow._enter_current_state()
        state = self.flow.public_state()
        self.assertEqual(state["services"]["call112"]["state"], "CONDITIONAL")
        self.assertFalse(state["services"]["call112"]["indicated"])

        state = self.flow.dispatch_event(EV_STABLE)
        self.assertEqual(state["state_id"], "MONITOR")
        self.assertIn(
            state["services"]["call112"]["state"],
            {"IDLE", "RETURN_TO_FLOW"},
        )
        self.assertFalse(state["services"]["call112"]["indicated"])

        self.flow.engine.restore("CHOKE_ADULT", {})
        self.flow._enter_current_state()
        state = self.flow.dispatch_event(EV_WORSENING)
        self.assertEqual(state["state_id"], "UNRESP_CALL")
        self.assertEqual(state["services"]["call112"]["state"], "REQUIRED_PROMPT")
        self.assertTrue(state["services"]["call112"]["indicated"])

    def test_final_event_keeps_session_id(self) -> None:
        state = self.enter_burn_cover()
        session_id = state["context"]["session_id"]
        self.flow.dispatch_event(EV_SKIP)
        self.dispatch_many(self.flow, EV_STABLE, EV_HANDOVER, EV_CLOSE_SESSION)
        state = self.flow.dispatch_event(EV_CLOSE_SESSION)
        self.assertEqual(state["mode"], "home")

        event_log = self.data_dir / "data" / "session_events.jsonl"
        records = [json.loads(line) for line in event_log.read_text().splitlines()]
        self.assertEqual(records[-1]["from"], "SESSION_END")
        self.assertEqual(records[-1]["to"], "IDLE")
        self.assertEqual(records[-1]["session_id"], session_id)

    def test_sync_payload_contains_inventory_instances_and_never_blocks_emergency(self) -> None:
        inserted_at = datetime.now(timezone.utc).isoformat()
        state = self.flow.update_inventory_instance(
            "DRESSING_K",
            quantity_available=1,
            lot="LOT-2026-A",
            expiry_date="2099-12-31",
            inserted_at=inserted_at,
            status="AVAILABLE",
        )
        sync = state["services"]["app_sync"]
        self.assertEqual(sync["state"], "DISCONNECTED")
        self.assertEqual(sync["queue_state"], "SYNC_PENDING")
        self.assertFalse(sync["blocks_emergency"])
        self.assertIn("queued_at", sync["pending_payload"])
        payload_instances = sync["pending_payload"]["inventory"]["instances"]
        instance = next(item for item in payload_instances if item["sku"] == "DRESSING_K")
        self.assertEqual(instance["quantity_available"], 1)
        self.assertEqual(instance["status"], "AVAILABLE")
        self.assertEqual(instance["lot"], "LOT-2026-A")
        self.assertEqual(instance["expiry_date"], "2099-12-31")
        self.assertIn("updated_at", instance)

        state = self.flow.start_emergency()
        self.assertEqual(state["state_id"], "EM_START")
        self.assertEqual(state["services"]["app_sync"]["queue_state"], "SYNC_PENDING")

    def test_schema_two_inventory_is_migrated_to_instances(self) -> None:
        state_path = self.data_dir / "data" / "session_state.json"
        snapshot = json.loads(state_path.read_text(encoding="utf-8"))
        inventory = snapshot["services"]["inventory"]
        inventory["stock"]["DRESSING_K"] = 0
        inventory["used"] = {"DRESSING_K": 1}
        inventory.pop("instances", None)
        inventory.pop("maintenance", None)
        inventory.pop("kit_status", None)
        inventory.pop("suspected_missing", None)
        snapshot["schema_version"] = 2
        snapshot["services"]["app_sync"] = {
            "state": "DISCONNECTED",
            "queue_state": "SYNC_PENDING",
            "pending_payload": inventory,
            "last_error": None,
        }
        state_path.write_text(json.dumps(snapshot), encoding="utf-8")

        restored, _, _ = create_runtime(ROOT, self.data_dir)
        state = restored.public_state()
        stored = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["schema_version"], 3)
        self.assertEqual(len(state["services"]["inventory"]["instances"]), 21)
        dressing = next(
            item
            for item in state["services"]["inventory"]["instances"]
            if item["sku"] == "DRESSING_K"
        )
        self.assertEqual(dressing["quantity_available"], 0)
        self.assertEqual(dressing["status"], "USED")
        self.assertIn(
            "inventory",
            state["services"]["app_sync"]["pending_payload"],
        )

    def test_every_v10_json_transition_is_still_executable(self) -> None:
        self.assertEqual(len(self.spec.states), 62)
        transition_count = 0
        for state_id, node in self.spec.states.items():
            for label, expected_target in node.get("next", {}).items():
                with self.subTest(state=state_id, label=label):
                    engine = ClinicalStateMachine(self.spec)
                    engine.restore(state_id, {})
                    event = event_for_button(state_id, node, label)
                    result = engine.dispatch(event)
                    self.assertTrue(result.transitioned)
                    self.assertEqual(result.state_id, expected_target)
                    transition_count += 1
        self.assertGreater(transition_count, 62)


if __name__ == "__main__":
    unittest.main()
