from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from resq_core.app import create_runtime, load_settings


ROOT = Path(__file__).resolve().parent
RESETTABLE_STATES = {"IDLE", "SESSION_END"}


class RuntimeResetError(RuntimeError):
    """Raised when a development reset would risk an active intervention."""


def reset_runtime_state(
    root_dir: Path = ROOT,
    runtime_dir: Path | None = None,
) -> dict[str, Any]:
    settings = load_settings(root_dir)
    runtime_root = runtime_dir or root_dir
    state_path = runtime_root / settings["persistence"]["state_file"]
    event_log_path = runtime_root / settings["persistence"]["event_log_file"]
    log_path = runtime_root / settings["logging"]["file"]

    _require_inactive_runtime(state_path)
    reset_paths = {
        state_path,
        state_path.with_suffix(state_path.suffix + ".tmp"),
        event_log_path,
        log_path,
    }
    if state_path.parent.exists():
        reset_paths.update(state_path.parent.glob("*.tmp"))
        reset_paths.update(state_path.parent.glob("*.cache"))
        reset_paths.update(state_path.parent.glob("sync*.json"))
    for path in reset_paths:
        if path.is_file():
            path.unlink()

    flow, _, _ = create_runtime(root_dir, runtime_root)
    state = flow.public_state()
    inventory = state["services"]["inventory"]
    if state["state_id"] != "IDLE":
        raise RuntimeResetError("Il reset non ha ricreato lo stato IDLE")
    if inventory["pending_use"] or inventory["used"]:
        raise RuntimeResetError("Il reset ha lasciato movimenti inventario")
    if state["services"]["app_sync"]["pending_payload"]:
        raise RuntimeResetError("Il reset ha lasciato una coda sync")
    return state


def _require_inactive_runtime(state_path: Path) -> None:
    if not state_path.exists():
        return
    try:
        snapshot = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeResetError(
            "Stato runtime illeggibile: reset rifiutato per sicurezza"
        ) from exc
    state_id = str(snapshot.get("state_id", ""))
    session_active = bool(snapshot.get("session", {}).get("active", False))
    if session_active or state_id not in RESETTABLE_STATES:
        raise RuntimeResetError(
            f"Reset rifiutato: sessione o recovery attiva nello stato {state_id}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset factory/development dei soli dati runtime ResQ",
    )
    parser.add_argument(
        "--confirm-reset",
        action="store_true",
        help="Conferma esplicitamente la cancellazione dei dati runtime",
    )
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=None,
        help="Root runtime alternativa, destinata ai test",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.confirm_reset:
        raise SystemExit("Reset non eseguito: usa --confirm-reset")
    try:
        state = reset_runtime_state(ROOT, args.runtime_dir)
    except RuntimeResetError as exc:
        raise SystemExit(str(exc)) from exc
    inventory = state["services"]["inventory"]
    print(
        json.dumps(
            {
                "state_id": state["state_id"],
                "kit_status": inventory["kit_status"],
                "sku_count": len(inventory["instances"]),
                "sync_queue": state["services"]["app_sync"]["queue_state"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
