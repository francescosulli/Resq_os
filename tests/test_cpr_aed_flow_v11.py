from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from resq_core.app import RUNTIME_SOURCE_FILENAMES, create_runtime
from resq_core.emergency_flow import FlowError
from resq_core.events import (
    EV_ABNORMAL_BREATHING,
    EV_AED_AVAILABLE,
    EV_CALL112_STARTED,
    EV_DONE,
    EV_NO,
    EV_OPERATOR_ACTIVE,
    EV_REPEAT,
    EV_START_EMERGENCY,
    EV_UNRESPONSIVE,
    EV_YES,
)
from resq_core.spec_loader import HandoffSpecLoader, SpecError


ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "config" / "handoff"
FIXTURES = ROOT / "tests" / "fixtures"


class CPRDAEFlowV11Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary_directory.name)
        self.flow, self.buttons, self.spec = create_runtime(ROOT, self.data_dir)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def enter_adult_cpr(self) -> dict:
        self.flow.start_emergency()
        state = self.flow.dispatch_event(EV_START_EMERGENCY)
        for event in (
            EV_YES,
            EV_NO,
            EV_NO,
            EV_UNRESPONSIVE,
            EV_CALL112_STARTED,
            "EV_SELECT_ADULT",
            EV_ABNORMAL_BREATHING,
        ):
            state = self.flow.dispatch_event(event)
        return state

    def enter_state(self, state_id: str) -> dict:
        self.flow.engine.restore(state_id, {"session_id": "aed-test"})
        self.flow._enter_current_state()
        return self.flow.public_state()

    def test_flow_10_to_11_diff_is_limited_to_adult_parallel_aed(self) -> None:
        baseline = json.loads(
            (FIXTURES / "ResQ_flow_nodes_v1_0_baseline.json").read_text(
                encoding="utf-8"
            )
        )
        flow_11 = json.loads(
            (FIXTURES / "ResQ_flow_nodes_v1_1_baseline.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(baseline["fixture_kind"], "test-only historical baseline")
        self.assertFalse(baseline["runtime_loadable"])
        self.assertEqual(flow_11["version"], "1.1")
        self.assertEqual(
            flow_11["status"],
            "prototype_clinical_flow_v1_1_not_clinically_certified",
        )
        self.assertEqual(set(baseline["all_state_ids"]), set(flow_11["states"]))
        prompt_payload = json.dumps(
            {
                state_id: node["prompt"]
                for state_id, node in sorted(flow_11["states"].items())
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(prompt_payload).hexdigest(),
            baseline["all_prompts_sha256"],
        )

        normalized = {
            state_id: copy.deepcopy(flow_11["states"][state_id])
            for state_id in baseline["states"]
        }
        normalized["ADULT_CPR"]["next"]["CONTINUA"] = "AED_AVAILABLE"
        normalized["ADULT_CPR"].pop("parallel_events")
        normalized["ADULT_CPR_LOOP"].pop("parallel_events")
        normalized["AED_AVAILABLE"].pop("compatibility_only")
        self.assertEqual(normalized, baseline["states"])

    def test_flow_11_to_12_diff_is_limited_to_pediatric_aed(self) -> None:
        baseline = json.loads(
            (FIXTURES / "ResQ_flow_nodes_v1_1_baseline.json").read_text(
                encoding="utf-8"
            )
        )
        flow_12 = json.loads(
            (HANDOFF / "ResQ_flow_nodes_v1_2.json").read_text(encoding="utf-8")
        )
        self.assertEqual(baseline["version"], "1.1")
        self.assertEqual(flow_12["version"], "1.2")
        self.assertEqual(set(baseline["states"]), set(flow_12["states"]))

        baseline_top = copy.deepcopy(baseline)
        current_top = copy.deepcopy(flow_12)
        baseline_states = baseline_top.pop("states")
        current_states = current_top.pop("states")
        baseline_top.pop("version")
        baseline_top.pop("status")
        current_top.pop("version")
        current_top.pop("status")
        self.assertEqual(current_top, baseline_top)

        authorized = {"PED_CPR", "PED_CPR_COMP_ONLY", "AED_USE"}
        for state_id in set(current_states) - authorized:
            self.assertEqual(current_states[state_id], baseline_states[state_id])
        for state_id in ("PED_CPR", "PED_CPR_COMP_ONLY"):
            normalized = copy.deepcopy(current_states[state_id])
            self.assertEqual(
                normalized.pop("parallel_events"),
                {EV_AED_AVAILABLE: "AED_USE"},
            )
            self.assertEqual(normalized, baseline_states[state_id])
        normalized_aed = copy.deepcopy(current_states["AED_USE"])
        self.assertEqual(
            set(normalized_aed.pop("aed_guidance_by_age_class")),
            {"UNKNOWN", "INFANT", "CHILD", "ADULT"},
        )
        self.assertEqual(normalized_aed, baseline_states["AED_USE"])

        self.assertNotIn(
            "ResQ_flow_nodes_v1_1_baseline.json",
            RUNTIME_SOURCE_FILENAMES,
        )
        with self.assertRaises(SpecError):
            HandoffSpecLoader(
                FIXTURES / "ResQ_flow_nodes_v1_1_baseline.json",
                HANDOFF / "ResQ_state_machine_spec_v1_2.yaml",
                HANDOFF / "ResQ_Automotive_BOM_v1_0.yaml",
            ).load()

    def test_adult_cpr_and_loop_accept_aed_without_continue(self) -> None:
        for state_id in ("ADULT_CPR", "ADULT_CPR_LOOP"):
            with self.subTest(state=state_id):
                state = self.enter_state(state_id)
                inventory_before = copy.deepcopy(state["services"]["inventory"])
                self.assertTrue(state["ux"]["metronome"]["active"])
                left = next(
                    key for key in state["soft_keys"] if key["position"] == "left"
                )
                self.assertEqual(
                    left["event"],
                    EV_AED_AVAILABLE,
                )
                self.assertTrue(left["touch_enabled"])
                self.assertTrue(left["physical_enabled"])
                self.assertFalse(state["ux"]["aed_reminder"]["visible"])

                state = self.flow.dispatch_event(EV_AED_AVAILABLE)
                self.assertEqual(state["state_id"], "AED_USE")
                self.assertTrue(state["context"]["aed_present"])
                self.assertEqual(
                    state["context"]["aed_return_state"],
                    "ADULT_CPR_LOOP",
                )
                self.assertFalse(state["ux"]["metronome"]["active"])
                self.assertEqual(state["services"]["inventory"], inventory_before)

                state = self.flow.dispatch_event(EV_DONE)
                self.assertEqual(state["state_id"], "ADULT_CPR_LOOP")
                self.assertTrue(state["ux"]["metronome"]["active"])

    def test_no_aed_event_keeps_cpr_continuous(self) -> None:
        state = self.enter_state("ADULT_CPR")
        self.assertFalse(state["context"]["aed_present"])
        state = self.flow.dispatch_event(EV_DONE)
        self.assertEqual(state["state_id"], "ADULT_CPR_LOOP")
        self.assertTrue(state["ux"]["metronome"]["active"])
        self.assertFalse(state["context"]["aed_present"])

    def test_pediatric_cpr_without_aed_keeps_availability_prompt_and_cta(self) -> None:
        for state_id in ("PED_CPR", "PED_CPR_COMP_ONLY"):
            with self.subTest(state=state_id):
                state = self.enter_state(state_id)
                self.assertFalse(state["context"]["aed_present"])
                self.assertIn("Usa il DAE appena disponibile.", state["prompt"])
                self.assertIn(
                    EV_AED_AVAILABLE,
                    [key["event"] for key in state["soft_keys"]],
                )
                self.assertEqual(
                    state["services"]["ui_audio"]["last_prompt"],
                    state["prompt"],
                )

    def test_pediatric_aed_lifecycle_updates_text_audio_and_badge(self) -> None:
        expected_prompts = {
            "PED_CPR": (
                "Continua con 30 compressioni e 2 ventilazioni. "
                "Frequenza 100–120/min; profondità circa un terzo del torace."
            ),
            "PED_CPR_COMP_ONLY": (
                "Se non riesci o non vuoi eseguire ventilazioni, continua con "
                "compressioni toraciche senza interromperti. Frequenza 100–120/min; "
                "profondità circa un terzo del torace."
            ),
        }
        for state_id, expected_prompt in expected_prompts.items():
            with self.subTest(state=state_id):
                self.enter_state(state_id)
                using_aed = self.flow.dispatch_event(EV_AED_AVAILABLE)
                self.assertEqual(using_aed["state_id"], "AED_USE")

                returned = self.flow.dispatch_event(EV_DONE)
                self.assertEqual(returned["state_id"], state_id)
                self.assertTrue(returned["context"]["aed_present"])
                self.assertEqual(returned["ux"]["aed_reminder"]["label"], "DAE PRESENTE")
                self.assertEqual(returned["prompt"], expected_prompt)
                self.assertNotIn("appena disponibile", returned["prompt"].lower())
                self.assertEqual(
                    returned["services"]["ui_audio"]["last_prompt"],
                    expected_prompt,
                )

    def test_repeat_after_pediatric_aed_uses_the_post_aed_prompt(self) -> None:
        repeat_actions = {
            "PED_CPR": self.flow.repeat_ux_audio,
            "PED_CPR_COMP_ONLY": lambda: self.flow.dispatch_event(EV_REPEAT),
        }
        for state_id, repeat in repeat_actions.items():
            with self.subTest(state=state_id):
                self.enter_state(state_id)
                self.flow.dispatch_event(EV_AED_AVAILABLE)
                returned = self.flow.dispatch_event(EV_DONE)
                sequence = returned["services"]["ui_audio"]["playback_sequence"]

                repeated = repeat()
                audio = repeated["services"]["ui_audio"]
                self.assertEqual(audio["last_prompt"], repeated["prompt"])
                self.assertNotIn("appena disponibile", audio["last_prompt"].lower())
                self.assertEqual(audio["playback_sequence"], sequence + 1)

    def test_adult_cpr_loop_after_aed_has_coherent_presentation(self) -> None:
        self.enter_state("ADULT_CPR")
        self.flow.dispatch_event(EV_AED_AVAILABLE)
        returned = self.flow.dispatch_event(EV_DONE)

        self.assertEqual(returned["state_id"], "ADULT_CPR_LOOP")
        self.assertTrue(returned["context"]["aed_present"])
        self.assertEqual(returned["ux"]["aed_reminder"]["label"], "DAE PRESENTE")
        self.assertNotIn("appena disponibile", returned["prompt"].lower())
        self.assertEqual(
            returned["services"]["ui_audio"]["last_prompt"],
            returned["prompt"],
        )

    def test_aed_return_restarts_metronome_and_preserves_112_operator(self) -> None:
        state = self.enter_adult_cpr()
        inventory_before = copy.deepcopy(state["services"]["inventory"])
        state = self.flow.dispatch_event(EV_OPERATOR_ACTIVE)
        self.assertTrue(state["services"]["call112"]["operator_active"])

        state = self.flow.dispatch_event(EV_AED_AVAILABLE)
        self.assertEqual(state["state_id"], "AED_USE")
        self.assertFalse(state["ux"]["metronome"]["active"])
        self.assertEqual(
            state["ux"]["call112"]["compact_label"],
            "SEGUI L'OPERATORE 112",
        )

        state = self.flow.dispatch_event(EV_DONE)
        self.assertEqual(state["state_id"], "ADULT_CPR_LOOP")
        self.assertTrue(state["ux"]["metronome"]["active"])
        self.assertTrue(state["services"]["call112"]["operator_active"])
        self.assertEqual(state["ux"]["aed_reminder"]["label"], "DAE PRESENTE")
        self.assertFalse(state["ux"]["aed_reminder"]["interactive"])
        self.assertNotIn(
            EV_AED_AVAILABLE,
            [key["event"] for key in state["soft_keys"]],
        )
        self.assertEqual(state["services"]["inventory"], inventory_before)
        with self.assertRaises(FlowError):
            self.flow.dispatch_event(EV_AED_AVAILABLE)

    def test_pediatric_cpr_uses_shared_aed_and_returns_to_origin(self) -> None:
        scenarios = {
            "PED_CPR": ("INFANT", "center"),
            "PED_CPR_COMP_ONLY": ("CHILD", "left"),
        }
        for state_id, (age_class, lane) in scenarios.items():
            with self.subTest(state=state_id):
                state = self.enter_state(state_id)
                self.flow.engine.context["age_class"] = age_class
                inventory_before = copy.deepcopy(state["services"]["inventory"])
                sequence_before = state["services"]["ui_audio"]["playback_sequence"]
                control = next(
                    key
                    for key in state["soft_keys"]
                    if key["event"] == EV_AED_AVAILABLE
                )
                self.assertEqual(control["position"], lane)
                self.assertTrue(control["touch_enabled"])
                self.assertTrue(control["physical_enabled"])
                self.buttons.configure_soft_keys(state["soft_keys"])
                self.assertEqual(
                    self.buttons.event_for_lane(lane),
                    EV_AED_AVAILABLE,
                )

                using_aed = self.flow.dispatch_event(EV_AED_AVAILABLE)
                self.assertEqual(using_aed["state_id"], "AED_USE")
                self.assertTrue(using_aed["context"]["aed_present"])
                self.assertEqual(using_aed["context"]["aed_return_state"], state_id)
                self.assertEqual(using_aed["context"]["age_class"], age_class)
                self.assertFalse(using_aed["ux"]["metronome"]["active"])
                self.assertEqual(
                    using_aed["services"]["ui_audio"]["playback_sequence"],
                    sequence_before + 1,
                )
                self.assertEqual(using_aed["services"]["inventory"], inventory_before)

                returned = self.flow.dispatch_event(EV_DONE)
                self.assertEqual(returned["state_id"], state_id)
                self.assertTrue(returned["ux"]["metronome"]["active"])
                self.assertEqual(returned["ux"]["aed_reminder"]["label"], "DAE PRESENTE")
                self.assertTrue(returned["ux"]["aed_reminder"]["visible"])
                self.assertNotIn(
                    EV_AED_AVAILABLE,
                    [key["event"] for key in returned["soft_keys"]],
                )
                self.assertEqual(
                    returned["services"]["ui_audio"]["playback_sequence"],
                    sequence_before + 2,
                )
                self.assertEqual(returned["services"]["inventory"], inventory_before)
                with self.assertRaises(FlowError):
                    self.flow.dispatch_event(EV_AED_AVAILABLE)

    def test_pediatric_aed_guidance_is_age_aware_without_shock_decisions(self) -> None:
        scenarios = {
            "INFANT": ("PED_CPR", "Usa la modalità pediatrica se disponibile."),
            "CHILD": (
                "PED_CPR",
                "Segui il DAE per scegliere la modalità corretta.",
            ),
            "ADULT": ("ADULT_CPR", "Usa la modalità standard."),
        }
        for age_class, (state_id, mode) in scenarios.items():
            with self.subTest(age_class=age_class):
                self.enter_state(state_id)
                self.flow.engine.context["age_class"] = age_class
                state = self.flow.dispatch_event(EV_AED_AVAILABLE)
                self.assertEqual(state["ux"]["aed_use"]["age_class"], age_class)
                self.assertEqual(state["ux"]["aed_use"]["guidance"]["mode"], mode)
                self.assertIn("segui le sue istruzioni", state["prompt"].lower())
                for forbidden in ("shock_required", "shockable_rhythm"):
                    self.assertNotIn(forbidden, state["context"])
        contract = self.spec.architecture["event_contracts"][EV_AED_AVAILABLE]
        self.assertEqual(
            set(contract["must_not_imply"]),
            {"shockable_rhythm", "shock_required", "aed_powered_on", "pads_attached"},
        )
        self.assertEqual(
            hashlib.sha256(
                (HANDOFF / "ResQ_Automotive_BOM_v1_0.yaml").read_bytes()
            ).hexdigest(),
            "61d08212f7cdb303ad3707bf2ffe58f6bf75f062915e1482c1580bb91e76ed0c",
        )
        self.assertEqual(
            hashlib.sha256(
                (HANDOFF / "ResQ_112_UX_v1_1.yaml").read_bytes()
            ).hexdigest(),
            "19a564081d99bc6ed4acce3a1059be5c0001410410108401d3370ae1ac3e6cc2",
        )

    def test_pediatric_aed_restart_and_operator_priority_preserve_return(self) -> None:
        self.enter_state("PED_CPR_COMP_ONLY")
        self.flow.engine.context["age_class"] = "CHILD"
        operator = self.flow.dispatch_event(EV_OPERATOR_ACTIVE)
        self.assertTrue(operator["services"]["call112"]["operator_active"])
        using_aed = self.flow.dispatch_event(EV_AED_AVAILABLE)
        self.assertEqual(using_aed["state_id"], "AED_USE")
        self.assertEqual(using_aed["context"]["aed_return_state"], "PED_CPR_COMP_ONLY")
        self.assertEqual(
            using_aed["ux"]["call112"]["compact_label"],
            "SEGUI L'OPERATORE 112",
        )

        restored, _, _ = create_runtime(ROOT, self.data_dir)
        self.assertTrue(restored.resume_required)
        resumed = restored.resume_session()
        self.assertEqual(resumed["state_id"], "AED_USE")
        self.assertEqual(resumed["context"]["aed_return_state"], "PED_CPR_COMP_ONLY")
        self.assertTrue(resumed["services"]["call112"]["operator_active"])
        returned = restored.dispatch_event(EV_DONE)
        self.assertEqual(returned["state_id"], "PED_CPR_COMP_ONLY")
        self.assertTrue(returned["ux"]["metronome"]["active"])
        self.assertTrue(returned["services"]["call112"]["operator_active"])

    def test_aed_available_state_is_compatibility_only(self) -> None:
        self.assertTrue(self.spec.states["AED_AVAILABLE"]["compatibility_only"])
        inbound = [
            (state_id, event)
            for state_id, node in self.spec.states.items()
            for event, target in {
                **node.get("next", {}),
                **node.get("parallel_events", {}),
            }.items()
            if target == "AED_AVAILABLE"
        ]
        self.assertEqual(inbound, [])

        state = self.enter_state("AED_AVAILABLE")
        self.assertFalse(state["context"]["aed_present"])
        state = self.flow.dispatch_event(EV_YES)
        self.assertEqual(state["state_id"], "AED_USE")
        self.assertTrue(state["context"]["aed_present"])

    def test_v10_snapshot_is_upgraded_without_inventory_changes(self) -> None:
        state_path = self.data_dir / "data" / "session_state.json"
        before = json.loads(state_path.read_text(encoding="utf-8"))
        before["spec_version"] = "1.0"
        inventory_before = copy.deepcopy(before["services"]["inventory"])
        state_path.write_text(json.dumps(before), encoding="utf-8")

        restored, _, _ = create_runtime(ROOT, self.data_dir)
        after = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(after["spec_version"], "1.2")
        self.assertEqual(after["services"]["inventory"], inventory_before)
        self.assertEqual(restored.public_state()["version"], "1.2")

    def test_v11_snapshot_is_upgraded_without_inventory_changes(self) -> None:
        state_path = self.data_dir / "data" / "session_state.json"
        before = json.loads(state_path.read_text(encoding="utf-8"))
        before["spec_version"] = "1.1"
        inventory_before = copy.deepcopy(before["services"]["inventory"])
        state_path.write_text(json.dumps(before), encoding="utf-8")

        restored, _, _ = create_runtime(ROOT, self.data_dir)
        after = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(after["spec_version"], "1.2")
        self.assertEqual(after["services"]["inventory"], inventory_before)
        self.assertEqual(restored.public_state()["version"], "1.2")


if __name__ == "__main__":
    unittest.main()
