from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from resq_core.app import create_runtime
from resq_core.emergency_flow import FlowError
from resq_core.events import (
    EV_ABNORMAL_BREATHING,
    EV_CALL112_STARTED,
    EV_CLOSE_SESSION,
    EV_DONE,
    EV_HANDOVER,
    EV_ITEM_TAKEN,
    EV_MATERIAL_NOT_FOUND,
    EV_MATERIAL_TAKEN,
    EV_NO,
    EV_NORMAL_BREATHING,
    EV_OPERATOR_ACTIVE,
    EV_PROBLEM,
    EV_REPEAT,
    EV_RESPONSIVE,
    EV_SKIP,
    EV_STABLE,
    EV_START_EMERGENCY,
    EV_UNKNOWN,
    EV_UNRESPONSIVE,
    EV_YES,
)


ROOT = Path(__file__).resolve().parents[1]


class V10ArchitectureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary_directory.name)
        self.flow, self.buttons, self.spec = create_runtime(ROOT, self.data_dir)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def dispatch_many(self, *events: str) -> dict:
        state = self.flow.public_state()
        for event in events:
            state = self.flow.dispatch_event(event)
        return state

    def enter_flow(self) -> dict:
        self.flow.start_emergency()
        return self.flow.dispatch_event(EV_START_EMERGENCY)

    def enter_adult_cpr(self) -> dict:
        self.enter_flow()
        return self.dispatch_many(
            EV_YES,
            EV_NO,
            EV_NO,
            EV_UNRESPONSIVE,
            EV_CALL112_STARTED,
            "EV_SELECT_ADULT",
            EV_ABNORMAL_BREATHING,
        )

    def enter_pediatric_face_shield(self) -> dict:
        self.enter_flow()
        return self.dispatch_many(
            EV_YES,
            EV_NO,
            EV_NO,
            EV_UNRESPONSIVE,
            EV_CALL112_STARTED,
            "EV_SELECT_INFANT",
            EV_ABNORMAL_BREATHING,
        )

    def enter_major_bleed_dressing(self) -> dict:
        self.enter_flow()
        return self.dispatch_many(EV_YES, EV_NO, EV_YES)

    def test_three_sources_validate_as_flow_12_bom_10_contract(self) -> None:
        self.assertEqual(self.spec.version, "1.2")
        self.assertEqual(self.spec.architecture["version"], "1.2")
        self.assertEqual(self.spec.bom["bom_version"], "1.0")
        self.assertEqual(len(self.spec.states), 62)
        self.assertEqual(len(self.spec.items), 21)
        self.assertEqual(len(self.spec.material_requests), 14)
        self.assertFalse(self.spec.flow["kit_policy"]["medicines_in_kit"])

        new_states = {
            "WOUND_PPE",
            "PED_FACE_SHIELD_OPTION",
            "PED_CPR_MODE",
            "PED_CPR_COMP_ONLY",
            "BURN_COVER",
            "LIMB_SUPPORT_OPTION",
        }
        self.assertTrue(new_states.issubset(self.spec.states))
        for node in self.spec.states.values():
            self.assertEqual(len(node["buttons"]), 3)
            self.assertLessEqual(len(node.get("materials", [])), 1)
            self.assertNotIn("sku", node)
            self.assertNotIn("slot", node)
            self.assertNotIn("led_id", node)
            if node.get("materials"):
                self.assertIn(node["materials"][0], self.spec.material_requests)
                self.assertIn(node["led_zone"], self.spec.zones)

    def test_new_clinical_targets_are_exactly_the_v10_json_targets(self) -> None:
        states = self.spec.states
        self.assertEqual(states["TRAUMA_SELECT"]["next"]["FERITA"], "WOUND_PPE")
        self.assertEqual(states["WOUND_PPE"]["next"]["SALTA"], "WOUND_CARE")
        self.assertEqual(states["BURN"]["next"]["FATTO"], "BURN_COVER")
        self.assertEqual(states["BURN_COVER"]["next"]["SALTA"], "MONITOR")
        self.assertEqual(
            states["LIMB_TRAUMA"]["next"]["FATTO"], "LIMB_SUPPORT_OPTION"
        )
        self.assertEqual(
            states["PED_BREATH_CHECK"]["next"]["NO"],
            "PED_FACE_SHIELD_OPTION",
        )
        self.assertEqual(
            states["PED_CPR_MODE"]["next"]["NO"], "PED_CPR_COMP_ONLY"
        )

    def test_missing_pediatric_face_shield_does_not_skip_rescue_breaths(self) -> None:
        self.flow.inventory.set_stock("CPR_FACE_SHIELD", 0)
        state = self.enter_pediatric_face_shield()
        self.assertEqual(state["state_id"], "PED_FACE_SHIELD_OPTION")
        self.assertEqual(state["services"]["materials"]["state"], "UNAVAILABLE")

        state = self.flow.dispatch_event(EV_SKIP)
        self.assertEqual(state["state_id"], "PED_5_BREATHS")
        self.assertEqual(state["services"]["inventory"]["pending_use"], {})

        state = self.flow.dispatch_event(EV_DONE)
        self.assertEqual(state["state_id"], "PED_CPR_MODE")
        state = self.flow.dispatch_event(EV_NO)
        self.assertEqual(state["state_id"], "PED_CPR_COMP_ONLY")

    def test_taken_pediatric_face_shield_is_optional_inventory(self) -> None:
        state = self.enter_pediatric_face_shield()
        resolved = state["services"]["materials"]["active_request"]["resolved"]
        self.assertEqual(resolved["sku"], "CPR_FACE_SHIELD")
        self.assertEqual(resolved["slot"], "QA_C")

        state = self.flow.dispatch_event(EV_ITEM_TAKEN)
        self.assertEqual(state["state_id"], "PED_5_BREATHS")
        self.assertEqual(
            state["services"]["inventory"]["pending_use"],
            {"CPR_FACE_SHIELD": 1},
        )
        state = self.flow.dispatch_event(EV_DONE)
        self.assertEqual(state["state_id"], "PED_CPR_MODE")
        state = self.flow.dispatch_event(EV_YES)
        self.assertEqual(state["state_id"], "PED_CPR")

    def test_material_service_exhausts_bom_fallbacks_before_flow_fallback(self) -> None:
        self.flow.inventory.set_stock("DRESSING_G", 0)
        state = self.enter_major_bleed_dressing()
        resolved = state["services"]["materials"]["active_request"]["resolved"]
        self.assertEqual(state["state_id"], "BLEED_DIRECT_PRESSURE")
        self.assertEqual(resolved["sku"], "DRESSING_M_C1")
        self.assertEqual(resolved["slot"], "C1_D")
        self.assertEqual(resolved["led_id"], "LED_C1")
        self.assertTrue(resolved["fallback_used"])

        state = self.flow.dispatch_event(EV_MATERIAL_NOT_FOUND)
        resolved = state["services"]["materials"]["active_request"]["resolved"]
        self.assertEqual(state["state_id"], "BLEED_DIRECT_PRESSURE")
        self.assertEqual(resolved["sku"], "STERILE_COMPRESS_10X10_C1")
        self.assertEqual(state["led_status"]["zone"], "C1_EMORRAGIE")

        state = self.flow.dispatch_event(EV_MATERIAL_NOT_FOUND)
        self.assertEqual(state["state_id"], "MAT_FALLBACK_BLEED")
        self.assertEqual(state["last_event"], "EV_MATERIAL_UNAVAILABLE")
        self.assertNotIn("sku", self.flow.engine.current_node())

    def test_physical_inventory_decrements_only_after_post_event_confirmation(self) -> None:
        state = self.enter_major_bleed_dressing()
        resolved = state["services"]["materials"]["active_request"]["resolved"]
        self.assertEqual(resolved["sku"], "DRESSING_G")

        state = self.flow.dispatch_event(EV_MATERIAL_TAKEN)
        self.assertEqual(state["state_id"], "BLEED_CONTROLLED")
        self.assertEqual(
            state["services"]["inventory"]["pending_use"], {"DRESSING_G": 1}
        )
        self.assertEqual(state["services"]["inventory"]["stock"]["DRESSING_G"], 1)

        state = self.dispatch_many(
            EV_YES,
            EV_RESPONSIVE,
            EV_YES,
            EV_YES,
            EV_DONE,
            EV_STABLE,
            EV_HANDOVER,
        )
        self.assertEqual(state["state_id"], "POST_EVENT_INVENTORY")
        self.assertEqual(state["services"]["inventory"]["stock"]["DRESSING_G"], 1)

        state = self.flow.dispatch_event(EV_PROBLEM)
        self.assertTrue(state["services"]["inventory"]["correction_enabled"])
        state = self.flow.correct_inventory("DRESSING_G", 0)
        self.assertEqual(state["services"]["inventory"]["pending_use"], {})
        state = self.flow.correct_inventory("DRESSING_G", 1)
        self.assertEqual(
            state["services"]["inventory"]["pending_use"], {"DRESSING_G": 1}
        )

        state = self.flow.dispatch_event(EV_CLOSE_SESSION)
        self.assertEqual(state["state_id"], "SESSION_END")
        self.assertEqual(state["services"]["inventory"]["used"], {"DRESSING_G": 1})
        self.assertEqual(state["services"]["inventory"]["stock"]["DRESSING_G"], 0)
        self.assertEqual(
            state["services"]["app_sync"]["queue_state"], "SYNC_PENDING"
        )

        state = self.flow.dispatch_event(EV_CLOSE_SESSION)
        self.assertEqual(state["mode"], "home")
        self.assertEqual(state["services"]["inventory"]["used"], {"DRESSING_G": 1})

    def test_reference_adult_bls_path_remains_source_driven(self) -> None:
        state = self.enter_adult_cpr()
        self.assertEqual(state["state_id"], "ADULT_CPR")
        self.assertEqual(state["context"]["age_class"], "ADULT")
        self.assertTrue(state["context"]["metronome_active"])
        self.assertTrue(state["services"]["call112"]["operator_priority"])

    def test_unknown_answer_uses_json_precautionary_target(self) -> None:
        self.enter_flow()
        state = self.flow.dispatch_event(EV_UNKNOWN)
        self.assertEqual(state["state_id"], "SCENE_UNSAFE")

    def test_service_events_do_not_bypass_clinical_soft_keys(self) -> None:
        self.flow.start_emergency()
        before = self.flow.public_state()["state_id"]
        repeated = self.flow.dispatch_event(EV_REPEAT)
        self.assertEqual(repeated["state_id"], before)
        operator = self.flow.dispatch_event(EV_OPERATOR_ACTIVE)
        self.assertEqual(operator["state_id"], before)

        self.flow.dispatch_event(EV_START_EMERGENCY)
        with self.assertRaises(FlowError):
            self.flow.repeat_audio()
        with self.assertRaises(FlowError):
            self.flow.run_diagnostic("led")

    def test_active_v10_session_requires_explicit_resume_after_restart(self) -> None:
        self.enter_adult_cpr()
        restored, _, _ = create_runtime(ROOT, self.data_dir)
        interrupted = restored.public_state()
        self.assertEqual(interrupted["mode"], "resume")
        self.assertEqual(interrupted["state_id"], "ADULT_CPR")

        resumed = restored.resume_session()
        self.assertEqual(resumed["mode"], "emergency")
        self.assertEqual(resumed["state_id"], "ADULT_CPR")
        self.assertTrue(resumed["services"]["ui_audio"]["metronome_active"])

    def test_idle_v05_snapshot_migrates_inventory_to_physical_skus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            state_path = data_dir / "data" / "session_state.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text(
                json.dumps(self._legacy_snapshot("IDLE", active=False)),
                encoding="utf-8",
            )

            migrated, _, _ = create_runtime(ROOT, data_dir)
            state = migrated.public_state()
            stored = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["mode"], "home")
            self.assertEqual(stored["schema_version"], 3)
            self.assertEqual(stored["spec_version"], "1.2")
            self.assertEqual(
                state["services"]["inventory"]["used"],
                {"GLOVES_NITRILE": 1, "DRESSING_G": 1},
            )
            self.assertEqual(
                state["services"]["app_sync"]["queue_state"], "SYNC_PENDING"
            )

    def test_active_v05_snapshot_cannot_be_resumed_implicitly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            state_path = data_dir / "data" / "session_state.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text(
                json.dumps(self._legacy_snapshot("SCENE_SAFE", active=True)),
                encoding="utf-8",
            )

            migrated, _, _ = create_runtime(ROOT, data_dir)
            state = migrated.public_state()
            self.assertEqual(state["mode"], "resume")
            self.assertIsNotNone(state["resume_blocked_reason"])
            self.assertEqual(
                [key["position"] for key in state["soft_keys"]],
                ["left"],
            )
            with self.assertRaises(FlowError):
                migrated.resume_session()
            discarded = migrated.discard_session()
            self.assertEqual(discarded["mode"], "home")
            self.assertEqual(discarded["version"], "1.2")

    def test_physical_buttons_and_event_log_remain_adapters(self) -> None:
        self.enter_flow()
        self.assertEqual(self.buttons.handle_button("left"), "left")
        self.assertEqual(self.buttons.handle_button("center"), "center")
        self.assertEqual(self.buttons.handle_button("right"), "right")
        self.assertIsNone(self.buttons.handle_button("no"))
        self.assertIsNone(self.buttons.handle_button("repeat"))
        self.assertIsNone(self.buttons.handle_button("yes"))
        state = self.flow.handle_soft_key("right")
        self.assertEqual(state["state_id"], "MULTI_CASUALTY")

        event_log = self.data_dir / "data" / "session_events.jsonl"
        records = [json.loads(line) for line in event_log.read_text().splitlines()]
        self.assertTrue(all(record["schema_version"] == 3 for record in records))
        self.assertEqual(records[-1]["to"], "MULTI_CASUALTY")

    @staticmethod
    def _legacy_snapshot(state_id: str, active: bool) -> dict:
        return {
            "schema_version": 1,
            "spec_version": "v0_5",
            "state_id": state_id,
            "context": {},
            "services": {
                "call112": {"state": "IDLE"},
                "materials": {"state": "IDLE", "active_requests": []},
                "inventory": {
                    "state": "SYNC_PENDING",
                    "pending_use": [],
                    "used": {"PPE_GLOVES": 1, "MAJOR_BLEED_DRESSING": 1},
                    "local_dirty": True,
                },
                "ui_audio": {},
                "app_sync": {"state": "DISCONNECTED", "queue_state": "SYNC_PENDING"},
            },
            "session": {"active": active, "started_at": None, "closed_at": None},
            "last_event": None,
        }


if __name__ == "__main__":
    unittest.main()
