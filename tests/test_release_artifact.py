from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from resq_core.app import create_runtime
from resq_core.events import (
    EV_CLOSE_SESSION,
    EV_DONE,
    EV_HANDOVER,
    EV_MATERIAL_TAKEN,
    EV_NO,
    EV_RESPONSIVE,
    EV_STABLE,
    EV_START_EMERGENCY,
    EV_YES,
)
from resq_core.state_manager import StatePersistenceError
from scripts.build_release import build_release


ROOT = Path(__file__).resolve().parents[1]


class FinalSessionCommitTest(unittest.TestCase):
    @staticmethod
    def dispatch_many(flow, *events: str) -> dict:
        state = flow.public_state()
        for event in events:
            state = flow.dispatch_event(event)
        return state

    def prepare_post_event(self, runtime_root: Path):
        flow, _, _ = create_runtime(ROOT, runtime_root)
        flow.start_emergency()
        flow.dispatch_event(EV_START_EMERGENCY)
        self.dispatch_many(flow, EV_YES, EV_NO, EV_YES)
        flow.dispatch_event(EV_MATERIAL_TAKEN)
        self.dispatch_many(
            flow,
            EV_YES,
            EV_RESPONSIVE,
            EV_YES,
            EV_YES,
            EV_DONE,
            EV_STABLE,
            EV_HANDOVER,
        )
        self.assertEqual(flow.engine.state_id, "POST_EVENT_INVENTORY")
        return flow

    def test_crash_before_final_state_commit_replays_pending_use_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            flow = self.prepare_post_event(runtime_root)
            with patch.object(
                flow.state,
                "_write_state",
                side_effect=StatePersistenceError("simulated crash before commit"),
            ):
                with self.assertRaises(StatePersistenceError):
                    flow.dispatch_event(EV_CLOSE_SESSION)

            restored, _, _ = create_runtime(ROOT, runtime_root)
            self.assertEqual(restored.engine.state_id, "POST_EVENT_INVENTORY")
            self.assertTrue(restored.resume_required)
            self.assertEqual(restored.inventory.stock["DRESSING_G"], 1)
            self.assertEqual(restored.inventory.pending_use, {"DRESSING_G": 1})
            restored.resume_session()
            state = restored.dispatch_event(EV_CLOSE_SESSION)
            self.assertEqual(state["state_id"], "SESSION_END")
            self.assertEqual(restored.inventory.stock["DRESSING_G"], 0)
            self.assertEqual(restored.inventory.used["DRESSING_G"], 1)

    def test_restart_recovers_committed_final_event_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            flow = self.prepare_post_event(runtime_root)
            session_id = flow.engine.context["session_id"]
            with patch.object(
                flow.state,
                "_write_event_records",
                side_effect=StatePersistenceError("simulated crash after state commit"),
            ):
                with self.assertRaises(StatePersistenceError):
                    flow.dispatch_event(EV_CLOSE_SESSION)

            stored = json.loads(
                (runtime_root / "data" / "session_state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(stored["state_id"], "SESSION_END")
            self.assertEqual(stored["_event_commit"]["session_id"], session_id)

            restored, _, _ = create_runtime(ROOT, runtime_root)
            self.assertEqual(restored.engine.state_id, "SESSION_END")
            self.assertFalse(restored.resume_required)
            self.assertEqual(restored.inventory.stock["DRESSING_G"], 0)
            self.assertEqual(restored.inventory.used["DRESSING_G"], 1)

            create_runtime(ROOT, runtime_root)
            records = self._event_records(runtime_root)
            final_records = [
                record
                for record in records
                if record["event"] == EV_CLOSE_SESSION
                and record["from"] == "POST_EVENT_INVENTORY"
            ]
            self.assertEqual(len(final_records), 1)
            self.assertEqual(final_records[0]["session_id"], session_id)
            self.assertTrue(final_records[0]["event_id"])

    def test_reset_home_is_one_coherent_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            flow = self.prepare_post_event(runtime_root)
            session_id = flow.engine.context["session_id"]
            flow.dispatch_event(EV_CLOSE_SESSION)
            used_before_home = dict(flow.inventory.used)

            with patch.object(flow.state, "save", wraps=flow.state.save) as save:
                state = flow.dispatch_event(EV_CLOSE_SESSION)
            self.assertEqual(save.call_count, 1)
            self.assertEqual(state["state_id"], "IDLE")
            self.assertFalse(state["session"]["active"])
            self.assertIsNone(state["context"]["session_id"])

            restored, _, _ = create_runtime(ROOT, runtime_root)
            self.assertEqual(restored.engine.state_id, "IDLE")
            self.assertFalse(restored.resume_required)
            self.assertEqual(restored.inventory.used, used_before_home)
            final = self._event_records(runtime_root)[-1]
            self.assertEqual(final["from"], "SESSION_END")
            self.assertEqual(final["to"], "IDLE")
            self.assertEqual(final["session_id"], session_id)

    @staticmethod
    def _event_records(runtime_root: Path) -> list[dict]:
        event_log = runtime_root / "data" / "session_events.jsonl"
        return [json.loads(line) for line in event_log.read_text().splitlines()]


class ReleaseArtifactTest(unittest.TestCase):
    def test_release_artifact_is_reproducible_and_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            artifact = build_release(ROOT, output)
            first_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            artifact = build_release(ROOT, output)
            second_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            self.assertEqual(first_digest, second_digest)
            self.assertEqual(artifact.name, "ResQ_Prototype_Architecture_v1.1.zip")

            with zipfile.ZipFile(artifact) as archive:
                self.assertIsNone(archive.testzip())
                names = archive.namelist()
                prefix = "ResQ_Prototype_Architecture_v1.1/"
                required = {
                    prefix + "README.md",
                    prefix + "main.py",
                    prefix + "install.sh",
                    prefix + "scripts/build_release.py",
                    prefix + "tests/test_release_freeze.py",
                    prefix + "tests/fixtures/ResQ_flow_nodes_v1_0_baseline.json",
                    prefix + "tests/fixtures/ResQ_flow_nodes_v1_1_baseline.json",
                    prefix + "config/release.json",
                    prefix + "config/handoff/ResQ_flow_nodes_v1_2.json",
                    prefix + "config/handoff/ResQ_state_machine_spec_v1_2.yaml",
                    prefix + "config/handoff/ResQ_Automotive_BOM_v1_0.yaml",
                    prefix + "config/handoff/ResQ_UX_spec_v1_1.yaml",
                    prefix + "config/handoff/ResQ_UI_tokens_v1_1.yaml",
                    prefix + "config/handoff/ResQ_112_UX_v1_1.yaml",
                    prefix + "config/handoff/ResQ_CPR_metronome_v1_1.yaml",
                    prefix + "docs/CHANGELOG_Flow_v1_1_to_v1_2.md",
                    prefix + "RELEASE_MANIFEST.json",
                }
                self.assertTrue(required.issubset(names))
                forbidden_parts = {
                    ".git",
                    ".idea",
                    ".pytest_cache",
                    ".venv",
                    ".vscode",
                    "__MACOSX",
                    "__pycache__",
                    "data",
                    "dist",
                    "logs",
                }
                self.assertFalse(
                    [name for name in names if forbidden_parts.intersection(Path(name).parts)]
                )
                self.assertFalse(
                    [
                        name
                        for name in names
                        if Path(name).name in {".DS_Store", ".env"}
                        or Path(name).suffix in {".pyc", ".tmp", ".cache", ".log"}
                    ]
                )
                self.assertNotIn(
                    prefix + "config/handoff/ResQ_flow_nodes_v0_5.json",
                    names,
                )
                self.assertNotIn(
                    prefix + "config/handoff/ResQ_flow_nodes_v1_0.json",
                    names,
                )
                self.assertNotIn(
                    prefix + "config/handoff/ResQ_state_machine_spec_v1_0.yaml",
                    names,
                )
                self.assertNotIn(
                    prefix + "config/handoff/ResQ_flow_nodes_v1_1.json",
                    names,
                )
                self.assertNotIn(
                    prefix + "config/handoff/ResQ_state_machine_spec_v1_1.yaml",
                    names,
                )
                self.assertNotIn(prefix + "resq_core/protocol_loader.py", names)
                self.assertNotIn(prefix + "docs/migration_v0_5.md", names)
                fixture = json.loads(
                    archive.read(
                        prefix
                        + "tests/fixtures/ResQ_flow_nodes_v1_0_baseline.json"
                    )
                )
                self.assertEqual(
                    fixture["fixture_kind"],
                    "test-only historical baseline",
                )
                self.assertFalse(fixture["runtime_loadable"])
                flow_11_fixture = json.loads(
                    archive.read(
                        prefix
                        + "tests/fixtures/ResQ_flow_nodes_v1_1_baseline.json"
                    )
                )
                self.assertEqual(flow_11_fixture["version"], "1.1")
                manifest = json.loads(
                    archive.read(prefix + "RELEASE_MANIFEST.json")
                )
                self.assertEqual(manifest["release"]["product"], "ResQ")
                self.assertEqual(
                    manifest["release"]["release"], "Prototype Architecture 1.1"
                )

    def test_full_suite_passes_from_extracted_release(self) -> None:
        if os.environ.get("RESQ_TESTING_EXTRACTED_ARTIFACT") == "1":
            self.assertTrue(
                (ROOT / "tests" / "fixtures" / "ResQ_flow_nodes_v1_0_baseline.json").is_file()
            )
            return

        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            artifact = build_release(ROOT, temporary)
            with zipfile.ZipFile(artifact) as archive:
                archive.extractall(temporary / "extracted")
            extracted_root = temporary / "extracted" / artifact.stem
            environment = os.environ.copy()
            environment["RESQ_TESTING_EXTRACTED_ARTIFACT"] = "1"
            result = subprocess.run(
                ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=extracted_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("OK", result.stderr)


if __name__ == "__main__":
    unittest.main()
