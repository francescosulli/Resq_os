from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from resq_core.app import create_runtime
from resq_core.events import (
    EV_AED_AVAILABLE,
    EV_CALL112_STARTED,
    EV_DONE,
    EV_OPERATOR_ACTIVE,
    EV_OPERATOR_ENDED,
    EV_REPEAT,
    EV_START_EMERGENCY,
)


ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "config" / "handoff"


class UXV11Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary_directory.name)
        self.flow, self.buttons, self.clinical = create_runtime(ROOT, self.data_dir)
        self.ux = self.flow.ux_spec

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def enter_state(self, state_id: str) -> dict:
        self.flow.engine.restore(state_id, {"session_id": "ux-test"})
        self.flow._enter_current_state()
        return self.flow.public_state()

    def test_all_62_states_have_exact_source_driven_controls(self) -> None:
        self.assertEqual(len(self.clinical.states), 62)
        self.assertEqual(set(self.ux.states), set(self.clinical.states))
        for state_id, presentation in self.ux.states.items():
            state = self.enter_state(state_id)
            rendered = {key["position"]: key for key in state["soft_keys"]}
            expected = presentation["primary_controls"]
            self.assertEqual(set(rendered), set(expected), state_id)
            self.assertGreaterEqual(len(rendered), 1, state_id)
            self.assertLessEqual(len(rendered), 3, state_id)
            for lane, control in expected.items():
                self.assertEqual(rendered[lane]["event"], control["semantic_event"])
                self.assertEqual(rendered[lane]["label"], control["display_label"])
                self.assertEqual(rendered[lane]["color_role"], control["color_role"])
                self.assertTrue(rendered[lane]["enabled"])

    def test_repeat_uses_center_only_with_one_other_action(self) -> None:
        for state_id, presentation in self.ux.states.items():
            controls = presentation["primary_controls"]
            repeat_lanes = [
                lane
                for lane, control in controls.items()
                if control["semantic_event"] == EV_REPEAT
            ]
            if presentation["repeat_mode"] == "center_softkey":
                self.assertEqual(repeat_lanes, ["center"], state_id)
                expected_count = 3 if EV_AED_AVAILABLE in {
                    control["semantic_event"] for control in controls.values()
                } else 2
                self.assertEqual(len(controls), expected_count, state_id)
            elif presentation["repeat_mode"] == "header_touch":
                self.assertEqual(repeat_lanes, [], state_id)

        scene = self.enter_state("SCENE_SAFE")
        self.assertEqual(scene["ux"]["repeat"]["placement"], "header")
        self.assertNotIn(EV_REPEAT, [key["event"] for key in scene["soft_keys"]])
        self.assertEqual(self.flow.repeat_ux_audio()["state_id"], "SCENE_SAFE")

    def test_inactive_physical_lane_has_no_event_or_feedback(self) -> None:
        state = self.enter_state("EM_START")
        self.buttons.configure_soft_keys(state["soft_keys"])
        self.assertEqual(self.buttons.event_for_lane("left"), "EV_CLOSE_SESSION")
        self.assertIsNone(self.buttons.event_for_lane("center"))
        self.assertEqual(self.buttons.event_for_lane("right"), "EV_START_EMERGENCY")

        before = self.buttons.feedback_snapshot()
        self.buttons.record_press("right", "EV_START_EMERGENCY")
        after = self.buttons.feedback_snapshot()
        self.assertEqual(after["sequence"], before["sequence"] + 1)
        self.assertEqual(after["lane"], "right")
        self.assertFalse(self.buttons.record_press("right", "EV_START_EMERGENCY"))

    def test_button_controller_is_positional_only(self) -> None:
        self.assertTrue(
            set(self.buttons.BUTTON_MAP.values()).issubset({"left", "center", "right"})
        )
        for semantic_alias in ("no", "yes", "si", "repeat", "start", "emergency"):
            self.assertNotIn(semantic_alias, self.buttons.BUTTON_MAP)
            self.assertIsNone(self.buttons.handle_button(semantic_alias))

    def test_touch_and_hardware_resolve_the_same_state_driven_event(self) -> None:
        for state_id in self.clinical.states:
            state = self.enter_state(state_id)
            self.buttons.configure_soft_keys(state["soft_keys"])
            touch_events = {
                control["position"]: control["event"]
                for control in state["soft_keys"]
            }
            for lane in ("left", "center", "right"):
                self.assertEqual(
                    self.buttons.event_for_lane(lane),
                    touch_events.get(lane),
                    state_id,
                )

    def test_adult_aed_is_the_same_left_touch_and_hardware_action(self) -> None:
        for state_id in ("ADULT_CPR", "ADULT_CPR_LOOP"):
            with self.subTest(state=state_id):
                state = self.enter_state(state_id)
                left = next(
                    key for key in state["soft_keys"] if key["position"] == "left"
                )
                self.assertEqual(left["label"], "DAE DISPONIBILE")
                self.assertEqual(left["event"], EV_AED_AVAILABLE)
                self.assertTrue(left["touch_enabled"])
                self.assertTrue(left["physical_enabled"])

                controller = type(self.buttons)()
                controller.configure_soft_keys(state["soft_keys"])
                physical_event = controller.event_for_lane("left")
                self.assertEqual(physical_event, left["event"])
                self.assertTrue(controller.record_press("left", physical_event))
                self.assertFalse(controller.record_press("left", physical_event))

                transitioned = self.flow.dispatch_event(physical_event)
                self.assertEqual(transitioned["state_id"], "AED_USE")
                self.assertTrue(transitioned["context"]["aed_present"])

    def test_optional_material_controls_distinguish_skip_and_fallback(self) -> None:
        for state_id in ("BURN_COVER", "LIMB_SUPPORT_OPTION"):
            controls = self.ux.states[state_id]["primary_controls"]
            self.assertEqual(controls["left"]["display_label"], "NON TROVO")
            self.assertEqual(
                controls["left"]["semantic_event"], "EV_MATERIAL_NOT_FOUND"
            )
            self.assertEqual(controls["center"]["display_label"], "SALTA")
            self.assertEqual(controls["center"]["semantic_event"], "EV_SKIP")
            self.assertIn(
                controls["right"]["display_label"],
                {"FATTO", "PRESO"},
            )

    def test_all_112_policies_have_distinct_presentations(self) -> None:
        state_by_policy = {}
        for state_id, node in self.clinical.states.items():
            policy = node.get("call112")
            if policy and policy not in state_by_policy:
                state_by_policy[policy] = state_id

        expected = {
            "CONDITIONAL": (False, "no_call_now_banner"),
            "RECOMMENDED": (True, "prominent_call_panel"),
            "RECOMMENDED_IMMEDIATE": (True, "call_now_panel"),
            "REQUIRED_PROMPT": (True, "call_now_focus"),
            "OPERATOR_PRIORITY": (True, "call_now_panel"),
        }
        self.assertEqual(set(state_by_policy), set(expected))
        for policy, state_id in state_by_policy.items():
            presentation = self.enter_state(state_id)["ux"]["call112"]
            self.assertEqual(presentation["visible"], expected[policy][0], policy)
            self.assertEqual(presentation["mode"], expected[policy][1], policy)
            if policy == "OPERATOR_PRIORITY":
                self.assertEqual(presentation["display_variant"], "compact")

    def test_call_now_then_112_compact_and_operator_compact(self) -> None:
        call_now = self.enter_state("UNRESP_CALL")
        call_presentation = call_now["ux"]["call112"]
        self.assertEqual(call_presentation["display_variant"], "call_now")
        self.assertEqual(call_presentation["headline"], "CHIAMA IL 112 ORA")
        self.assertEqual(len(call_presentation["briefing"]["items"]), 5)
        self.assertTrue(
            all(item["text"] is None for item in call_presentation["briefing"]["items"])
        )
        self.assertTrue(
            all(
                item["fallback_prompt"] and item["display_fallback"]
                for item in call_presentation["briefing"]["items"]
            )
        )

        calling = self.flow.dispatch_event(EV_CALL112_STARTED)
        self.assertEqual(calling["ux"]["call112"]["display_variant"], "compact")
        self.assertEqual(calling["ux"]["call112"]["compact_label"], "112 IN CORSO")
        self.assertIsNone(calling["ux"]["call112"]["briefing"])

        self.flow.engine.restore("ADULT_CPR", {"session_id": "ux-test"})
        self.flow._enter_current_state()
        cpr = self.flow.public_state()
        self.assertEqual(cpr["ux"]["call112"]["display_variant"], "compact")
        operator = self.flow.dispatch_event(EV_OPERATOR_ACTIVE)
        self.assertEqual(
            operator["ux"]["call112"]["display_variant"], "compact_operator"
        )
        self.assertEqual(
            operator["ux"]["call112"]["compact_label"],
            "SEGUI L'OPERATORE 112",
        )

    def test_112_brief_uses_only_observed_values(self) -> None:
        state = self.enter_state("UNRESP_CALL")
        briefing = state["ux"]["call112"]["briefing"]
        self.assertIsNotNone(briefing)
        self.assertEqual(briefing["title"], "COSA COMUNICARE")
        self.assertTrue(all(not item["observed"] for item in briefing["items"]))
        self.assertTrue(
            all(
                item["text"] is None and item["display_fallback"]
                for item in briefing["items"]
            )
        )
        observations = state["services"]["emergency_brief"]["observations"]
        self.assertTrue(all(value is None for value in observations.values()))
        fallback_values = {
            value
            for item in briefing["items"]
            for value in (item["fallback_prompt"], item["display_fallback"])
        }
        self.assertTrue(fallback_values.isdisjoint(observations.values()))
        self.assertTrue(
            state["services"]["emergency_brief"][
                "must_not_affect_clinical_transitions"
            ]
        )

    def test_112_brief_observed_value_replaces_display_fallback(self) -> None:
        self.enter_state("UNRESP_CALL")
        self.flow.emergency_brief.observe(
            "RESPONSIVE",
            "EV_UNRESPONSIVE",
            "UNRESP_CALL",
        )
        state = self.flow.public_state()
        items = {
            item["id"]: item
            for item in state["ux"]["call112"]["briefing"]["items"]
        }
        self.assertTrue(items["condition"]["observed"])
        self.assertEqual(items["condition"]["text"], "Non risponde")
        self.assertNotEqual(
            items["condition"]["text"],
            items["condition"]["display_fallback"],
        )
        self.assertFalse(items["where"]["observed"])
        self.assertIsNone(items["where"]["text"])
        self.assertEqual(items["where"]["display_fallback"], "Comunica la posizione")

    def test_112_people_icon_is_neutral_and_non_numeric(self) -> None:
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('people: "2+"', javascript)
        self.assertIn('people: "👥"', javascript)
        self.assertIn("people: CONTROL_ICONS.people", javascript)

    def test_operator_event_controls_voice_repeat_and_metronome_ducking(self) -> None:
        self.enter_state("ADULT_CPR")
        active = self.flow.dispatch_event(EV_OPERATOR_ACTIVE)
        self.assertTrue(active["ux"]["call112"]["operator_active"])
        self.assertEqual(active["ux"]["call112"]["mode"], "operator_priority")
        self.assertFalse(active["ux"]["repeat"]["enabled"])
        self.assertNotIn(EV_REPEAT, [key["event"] for key in active["soft_keys"]])
        self.assertTrue(active["services"]["ui_audio"]["voice_suppressed"])
        self.assertTrue(active["ux"]["metronome"]["operator_ducked"])
        self.assertEqual(active["ux"]["metronome"]["duck_db"], -12)

        ended = self.flow.dispatch_event(EV_OPERATOR_ENDED)
        self.assertFalse(ended["services"]["ui_audio"]["voice_suppressed"])
        self.assertFalse(ended["ux"]["metronome"]["operator_ducked"])

    def test_audio_commands_cover_enter_repeat_transition_and_operator(self) -> None:
        audio = self.flow.ui_audio.audio
        entered = self.flow.start_emergency()
        first_sequence = entered["services"]["ui_audio"]["playback_sequence"]
        self.assertEqual(entered["services"]["ui_audio"]["playback_command"], "SPEAK")
        self.assertEqual(audio.current_instruction, entered["prompt"])

        scene = self.flow.dispatch_event(EV_START_EMERGENCY)
        self.assertGreater(
            scene["services"]["ui_audio"]["playback_sequence"], first_sequence
        )
        self.assertGreaterEqual(audio.stop_count, 2)
        playback_before_repeat = audio.playback_count
        repeated = self.flow.repeat_ux_audio()
        self.assertEqual(repeated["state_id"], "SCENE_SAFE")
        self.assertEqual(audio.playback_count, playback_before_repeat + 1)

        operator = self.flow.dispatch_event(EV_OPERATOR_ACTIVE)
        self.assertEqual(
            operator["services"]["ui_audio"]["playback_command"], "SUSPEND"
        )
        self.assertEqual(audio.current_instruction, "")

    def test_metronome_is_limited_to_four_source_states(self) -> None:
        enabled = {
            "ADULT_CPR",
            "ADULT_CPR_LOOP",
            "PED_CPR",
            "PED_CPR_COMP_ONLY",
        }
        actual = set()
        for state_id in self.clinical.states:
            metronome = self.enter_state(state_id)["ux"]["metronome"]
            if metronome["active"]:
                actual.add(state_id)
                self.assertEqual(metronome["target_bpm"], 110)
                self.assertFalse(metronome["automatic_30_2"])
        self.assertEqual(actual, enabled)

    def test_critical_cpr_has_source_driven_aed_control(self) -> None:
        cpr_states = {
            "ADULT_CPR": "left",
            "ADULT_CPR_LOOP": "left",
            "PED_CPR": "center",
            "PED_CPR_COMP_ONLY": "left",
        }
        for state_id, expected_lane in cpr_states.items():
            state = self.enter_state(state_id)
            self.assertEqual(state["ux"]["screen_mode"], "CRITICAL_ACTION")
            reminder = state["ux"]["aed_reminder"]
            self.assertFalse(reminder["visible"])
            self.assertEqual(reminder["label"], "DAE DISPONIBILE")
            self.assertFalse(reminder["interactive"])
            self.assertIsNone(reminder["event"])
            self.assertTrue(reminder["physical_enabled"])
            self.assertEqual(reminder["physical_lane"], expected_lane)
            cta = next(
                key
                for key in state["soft_keys"]
                if key["position"] == expected_lane
            )
            self.assertEqual(cta["event"], EV_AED_AVAILABLE)
            self.assertTrue(cta["touch_enabled"])
            self.assertTrue(cta["physical_enabled"])

        self.assertEqual(
            self.clinical.states["ADULT_CPR"]["next"],
            {"CONTINUA": "ADULT_CPR_LOOP"},
        )
        for state_id in cpr_states:
            self.assertEqual(
                self.clinical.states[state_id]["parallel_events"],
                {EV_AED_AVAILABLE: "AED_USE"},
            )

        self.enter_state("ADULT_CPR")
        exited = self.flow.dispatch_event(EV_DONE)
        self.assertEqual(exited["state_id"], "ADULT_CPR_LOOP")
        self.assertTrue(exited["ux"]["metronome"]["active"])

    def test_screen_modes_and_color_grammar_cover_all_states(self) -> None:
        for state_id, presentation in self.ux.states.items():
            self.assertIn(
                presentation["screen_mode"],
                {"EVALUATION", "ACTION", "CRITICAL_ACTION", "CALL_112"},
                state_id,
            )
            controls = presentation["primary_controls"].values()
            if presentation["state_type"] == "decision":
                colors = {control["display_label"]: control["color_role"] for control in controls}
                self.assertEqual(colors["NO"], "danger", state_id)
                self.assertEqual(colors["NON SO"], "warning", state_id)
                self.assertEqual(colors["SÌ"], "danger", state_id)

        expected_roles = {
            "FATTO": "success",
            "NON TROVO": "danger",
            "RIPETI": "support",
        }
        for label, expected in expected_roles.items():
            roles = {
                control["color_role"]
                for state in self.ux.states.values()
                for control in state["primary_controls"].values()
                if control["display_label"] == label
            }
            self.assertEqual(roles, {expected}, label)

    def test_frontend_uses_audio_clock_and_semantic_colors(self) -> None:
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        stylesheet = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("window.AudioContext", javascript)
        self.assertIn("this.nextBeatAt += 60 / this.bpm", javascript)
        self.assertIn("if (this.active) return", javascript)
        self.assertIn("compressionMetronome.stop()", javascript)
        self.assertIn("soft-key-lane lane-empty", javascript)
        self.assertNotIn("soft-key-button empty", javascript)
        soft_key_source = javascript.split("function softKeysMarkup", 1)[1].split(
            "function kitStatusLabel", 1
        )[0]
        self.assertNotIn("LANE_NUMBER", javascript)
        self.assertNotIn("<small>", soft_key_source)
        self.assertIn("class AudioGuideService", javascript)
        self.assertIn("SpeechSynthesisUtterance", javascript)
        self.assertIn("window.speechSynthesis.cancel()", javascript)
        self.assertIn("data-screen-mode", javascript)
        self.assertIn("DAE APPENA DISPONIBILE", javascript)
        self.assertIn("DAE DISPONIBILE", javascript)
        self.assertIn('lightning: "⚡"', javascript)
        self.assertIn("aed-reminder", javascript)
        self.assertIn("aed-use-guide", javascript)
        self.assertIn("sendLaneEvent", javascript)
        self.assertIn("const detail = item.observed && item.text", javascript)
        self.assertIn(": item.display_fallback || item.fallback_prompt", javascript)
        self.assertNotIn("call-supporting-instruction", javascript)
        self.assertNotIn("Indica Comune", javascript)
        for color in ("#b42318", "#8a4b08", "#067647", "#175cd3", "#475467"):
            self.assertIn(color, stylesheet.lower())

    def test_release_hashes_cover_clinical_12_bom_10_and_presentation_11(self) -> None:
        metadata = json.loads((ROOT / "config" / "release.json").read_text())
        self.assertEqual(metadata["release"], "Prototype Architecture 1.1")
        self.assertEqual(metadata["clinical_flow"], "1.2")
        self.assertEqual(metadata["state_machine"], "1.2")
        self.assertEqual(metadata["automotive_bom"], "1.0")
        self.assertEqual(metadata["ux_human_factors"], "1.1")
        for group in ("source_of_truth", "presentation_sources"):
            for source in metadata[group].values():
                digest = hashlib.sha256(
                    (HANDOFF / source["filename"]).read_bytes()
                ).hexdigest()
                self.assertEqual(digest, source["sha256"])


if __name__ == "__main__":
    unittest.main()
