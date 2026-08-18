from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from reset_runtime_state import RuntimeResetError, reset_runtime_state
from resq_core.app import (
    RELEASE_METADATA,
    RUNTIME_SOURCE_FILENAMES,
    create_runtime,
    load_settings,
)
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
from resq_core.services.inventory import InventoryService
from resq_core.services.readiness import ReadinessPolicy
from resq_core.state_manager import StateManager, StatePersistenceError


ROOT = Path(__file__).resolve().parents[1]


class ReleaseFreezeTest(unittest.TestCase):
    @staticmethod
    def dispatch_many(flow, *events: str) -> dict:
        state = flow.public_state()
        for event in events:
            state = flow.dispatch_event(event)
        return state

    def enter_major_bleed(self, flow) -> dict:
        flow.start_emergency()
        flow.dispatch_event(EV_START_EMERGENCY)
        return self.dispatch_many(flow, EV_YES, EV_NO, EV_YES)

    def reach_post_event(self, flow) -> dict:
        return self.dispatch_many(
            flow,
            EV_YES,
            EV_RESPONSIVE,
            EV_YES,
            EV_YES,
            EV_DONE,
            EV_STABLE,
            EV_HANDOVER,
        )

    def test_fresh_install_initializes_every_instance_from_bom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory) / "never-created"
            self.assertFalse(runtime_root.exists())
            flow, _, spec = create_runtime(ROOT, runtime_root)
            state = flow.public_state()
            inventory = state["services"]["inventory"]

            self.assertTrue((runtime_root / "data" / "session_state.json").is_file())
            self.assertEqual(state["state_id"], "IDLE")
            self.assertEqual(inventory["kit_status"], "MAINTENANCE")
            self.assertEqual(len(inventory["instances"]), len(spec.items))
            self.assertEqual(inventory["used"], {})
            self.assertEqual(inventory["pending_use"], {})
            self.assertFalse(state["session"]["active"])
            self.assertIsNone(state["services"]["app_sync"]["pending_payload"])
            tourniquet = next(
                instance
                for instance in inventory["instances"]
                if instance["sku"] == "TOURNIQUET_COMMERCIAL"
            )
            self.assertEqual(tourniquet["quantity_available"], 1)
            self.assertEqual(tourniquet["status"], "AVAILABLE")
            for instance in inventory["instances"]:
                expected = int(spec.items[instance["sku"]]["quantity_expected"])
                self.assertEqual(instance["quantity_available"], expected)
                self.assertEqual(instance["status"], "AVAILABLE")
                self.assertEqual(instance["lot"], "")
                self.assertIsNone(instance["expiry_date"])

    def test_release_tree_does_not_track_or_install_runtime_artifacts(self) -> None:
        if (ROOT / ".git").exists():
            packaged_files = subprocess.run(
                ["git", "ls-files"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
        else:
            packaged_files = [
                path.relative_to(ROOT).as_posix()
                for path in ROOT.rglob("*")
                if path.is_file()
            ]
        forbidden = {
            "data/session_state.json",
            "data/session_events.jsonl",
            "logs/resq.log",
        }
        self.assertTrue(forbidden.isdisjoint(packaged_files))
        install_script = (ROOT / "install.sh").read_text(encoding="utf-8")
        for exclusion in ("data/", "logs/", "__pycache__", "*.pyc", "*.tmp"):
            self.assertIn(f'--exclude "{exclusion}"', install_script)

    def test_factory_reset_restores_bom_state_and_clears_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            flow, _, spec = create_runtime(ROOT, runtime_root)
            now = datetime.now(timezone.utc).isoformat()
            flow.update_inventory_instance(
                "DRESSING_K",
                quantity_available=0,
                lot="TEST-LOT",
                expiry_date="2000-01-01",
                inserted_at=now,
                status="MISSING",
            )
            event_log = runtime_root / "data" / "session_events.jsonl"
            self.assertTrue(event_log.exists())

            state = reset_runtime_state(ROOT, runtime_root)
            inventory = state["services"]["inventory"]
            self.assertFalse(event_log.exists())
            self.assertEqual(inventory["used"], {})
            self.assertEqual(inventory["pending_use"], {})
            self.assertIsNone(state["services"]["app_sync"]["pending_payload"])
            for instance in inventory["instances"]:
                self.assertEqual(
                    instance["quantity_available"],
                    int(spec.items[instance["sku"]]["quantity_expected"]),
                )

    def test_factory_reset_refuses_active_emergency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            flow, _, _ = create_runtime(ROOT, runtime_root)
            flow.start_emergency()
            with self.assertRaises(RuntimeResetError):
                reset_runtime_state(ROOT, runtime_root)
            restored, _, _ = create_runtime(ROOT, runtime_root)
            self.assertTrue(restored.resume_required)
            self.assertEqual(restored.engine.state_id, "EM_START")

    def test_inventory_quantities_are_bounded_by_bom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            flow, _, spec = create_runtime(ROOT, Path(directory))
            expected = int(spec.items["DRESSING_K"]["quantity_expected"])
            with self.assertRaises(ValueError):
                flow.inventory.set_stock("DRESSING_K", -1)
            with self.assertRaises(ValueError):
                flow.inventory.set_stock("DRESSING_K", expected + 1)
            with self.assertRaises(ValueError):
                flow.inventory.update_instance(
                    "DRESSING_K",
                    quantity_available=expected + 1,
                    lot="",
                    expiry_date=None,
                    inserted_at=datetime.now(timezone.utc).isoformat(),
                    status="AVAILABLE",
                )
            self.assertEqual(flow.inventory.stock["DRESSING_K"], expected)

    def test_expired_and_non_tracked_expiry_are_coherent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            flow, _, _ = create_runtime(ROOT, Path(directory))
            now = datetime.now(timezone.utc).isoformat()
            flow.inventory.update_instance(
                "DRESSING_K",
                quantity_available=1,
                lot="OLD",
                expiry_date="2000-01-01",
                inserted_at=now,
                status="AVAILABLE",
            )
            flow.inventory.update_instance(
                "SCISSORS_FIRST_AID",
                quantity_available=1,
                lot="METAL",
                expiry_date="2000-01-01",
                inserted_at=now,
                status="AVAILABLE",
            )
            items = {
                item["sku"]: item
                for item in flow.inventory.maintenance_snapshot()["instances"]
            }
            self.assertEqual(items["DRESSING_K"]["status"], "EXPIRED")
            self.assertEqual(items["DRESSING_K"]["expiry_status"], "EXPIRED")
            self.assertEqual(
                items["SCISSORS_FIRST_AID"]["expiry_status"],
                "NOT_TRACKED",
            )
            self.assertEqual(items["SCISSORS_FIRST_AID"]["status"], "AVAILABLE")

    def test_readiness_policy_is_centralized_and_configurable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            flow, _, _ = create_runtime(ROOT, Path(directory))
            policy = ReadinessPolicy(critical_shortage_status="REFILL_REQUIRED")
            inventory = InventoryService(flow.inventory.catalog, policy)
            inventory.set_stock("TOURNIQUET_COMMERCIAL", 0)
            self.assertEqual(
                inventory.maintenance_snapshot()["kit_status"],
                "REFILL_REQUIRED",
            )

    def test_atomic_state_write_preserves_previous_snapshot_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            event_path = Path(directory) / "events.jsonl"
            initial = {"state_id": "IDLE", "value": 1}
            manager = StateManager(initial, state_path, event_path)
            manager.save(initial)

            with patch("resq_core.state_manager.os.replace", side_effect=OSError("stop")):
                with self.assertRaises(StatePersistenceError):
                    manager.save({"state_id": "IDLE", "value": 2})

            stored = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["value"], 1)
            self.assertEqual(manager.snapshot()["value"], 1)
            self.assertFalse((Path(directory) / "state.json.tmp").exists())

    def test_restart_during_emergency_and_pending_use_does_not_consume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            flow, _, _ = create_runtime(ROOT, runtime_root)
            flow.start_emergency()
            flow.dispatch_event(EV_START_EMERGENCY)
            restored, _, _ = create_runtime(ROOT, runtime_root)
            self.assertTrue(restored.resume_required)
            self.assertEqual(restored.engine.state_id, "SCENE_SAFE")

        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            flow, _, _ = create_runtime(ROOT, runtime_root)
            self.enter_major_bleed(flow)
            flow.dispatch_event(EV_MATERIAL_TAKEN)
            before = flow.inventory.stock["DRESSING_G"]
            restored, _, _ = create_runtime(ROOT, runtime_root)
            self.assertEqual(restored.inventory.stock["DRESSING_G"], before)
            self.assertEqual(restored.inventory.pending_use, {"DRESSING_G": 1})
            self.assertTrue(restored.resume_required)

    def test_post_event_restart_cannot_decrement_twice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            flow, _, _ = create_runtime(ROOT, runtime_root)
            self.enter_major_bleed(flow)
            flow.dispatch_event(EV_MATERIAL_TAKEN)
            state = self.reach_post_event(flow)
            self.assertEqual(state["state_id"], "POST_EVENT_INVENTORY")
            self.assertEqual(flow.inventory.stock["DRESSING_G"], 1)

            restored, _, _ = create_runtime(ROOT, runtime_root)
            self.assertTrue(restored.resume_required)
            restored.resume_session()
            state = restored.dispatch_event(EV_CLOSE_SESSION)
            self.assertEqual(state["state_id"], "SESSION_END")
            self.assertEqual(state["services"]["inventory"]["stock"]["DRESSING_G"], 0)

            after_confirmation, _, _ = create_runtime(ROOT, runtime_root)
            self.assertFalse(after_confirmation.resume_required)
            self.assertEqual(after_confirmation.inventory.stock["DRESSING_G"], 0)
            after_confirmation.dispatch_event(EV_CLOSE_SESSION)
            after_home, _, _ = create_runtime(ROOT, runtime_root)
            self.assertEqual(after_home.inventory.stock["DRESSING_G"], 0)
            self.assertEqual(after_home.inventory.used["DRESSING_G"], 1)

    def test_sync_queue_survives_restart_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            flow, _, _ = create_runtime(ROOT, runtime_root)
            now = datetime.now(timezone.utc).isoformat()
            state = flow.update_inventory_instance(
                "DRESSING_K",
                quantity_available=1,
                lot="SYNC-LOT",
                expiry_date="2099-12-31",
                inserted_at=now,
                status="AVAILABLE",
            )
            first_payload = state["services"]["app_sync"]["pending_payload"]
            first_key = first_payload["idempotency_key"]
            first_time = first_payload["queued_at"]
            duplicate_key = flow.app_sync.queue_sync(flow.inventory.snapshot())
            self.assertEqual(duplicate_key, first_key)
            self.assertEqual(flow.app_sync.pending_payload["queued_at"], first_time)

            restored, _, _ = create_runtime(ROOT, runtime_root)
            sync = restored.public_state()["services"]["app_sync"]
            self.assertEqual(sync["queue_state"], "SYNC_PENDING")
            self.assertEqual(sync["pending_payload"]["idempotency_key"], first_key)
            self.assertEqual(sync["pending_payload"]["queued_at"], first_time)
            self.assertFalse(sync["blocks_emergency"])
            self.assertFalse(restored.app_sync.mark_synced("stale-operation"))
            state = restored.start_emergency()
            self.assertEqual(state["state_id"], "EM_START")

    def test_runtime_sources_and_release_metadata_use_flow_12_bom_10(self) -> None:
        self.assertEqual(
            RUNTIME_SOURCE_FILENAMES,
            (
                "ResQ_flow_nodes_v1_2.json",
                "ResQ_state_machine_spec_v1_2.yaml",
                "ResQ_Automotive_BOM_v1_0.yaml",
            ),
        )
        self.assertNotIn("v0_5", " ".join(RUNTIME_SOURCE_FILENAMES))
        self.assertNotIn("v1_0_baseline", " ".join(RUNTIME_SOURCE_FILENAMES))
        fixture = ROOT / "tests" / "fixtures" / "ResQ_flow_nodes_v1_0_baseline.json"
        self.assertTrue(fixture.is_file())
        self.assertNotEqual(fixture.parent, ROOT / "config" / "handoff")
        flow_11_fixture = (
            ROOT / "tests" / "fixtures" / "ResQ_flow_nodes_v1_1_baseline.json"
        )
        self.assertTrue(flow_11_fixture.is_file())
        self.assertNotEqual(flow_11_fixture.parent, ROOT / "config" / "handoff")
        self.assertEqual(RELEASE_METADATA["product"], "ResQ")
        self.assertEqual(RELEASE_METADATA["release"], "Prototype Architecture 1.1")
        self.assertEqual(RELEASE_METADATA["clinical_flow"], "1.2")
        self.assertEqual(RELEASE_METADATA["state_machine"], "1.2")
        self.assertEqual(RELEASE_METADATA["automotive_bom"], "1.0")
        self.assertEqual(RELEASE_METADATA["ux_human_factors"], "1.1")
        self.assertEqual(RELEASE_METADATA["resq_connect_transport"], "not_implemented")
        self.assertFalse(RELEASE_METADATA["clinically_certified"])
        for source in RELEASE_METADATA["source_of_truth"].values():
            path = ROOT / "config" / "handoff" / source["filename"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source["sha256"])
        for source in RELEASE_METADATA["presentation_sources"].values():
            path = ROOT / "config" / "handoff" / source["filename"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source["sha256"])

    def test_default_server_host_is_localhost(self) -> None:
        settings = load_settings(ROOT)
        self.assertEqual(settings["app"]["host"], "127.0.0.1")
        service = (ROOT / "system" / "resq.service").read_text(encoding="utf-8")
        self.assertIn("--host 127.0.0.1", service)


if __name__ == "__main__":
    unittest.main()
