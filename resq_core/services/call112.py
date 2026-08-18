from __future__ import annotations

import copy
from typing import Any

from resq_core.events import (
    EV_CALL112_STARTED,
    EV_OPERATOR_ACTIVE,
    EV_OPERATOR_ENDED,
)


class Call112Service:
    POLICIES = {
        "CONDITIONAL",
        "RECOMMENDED",
        "RECOMMENDED_IMMEDIATE",
        "REQUIRED_PROMPT",
        "OPERATOR_PRIORITY",
    }

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state = "IDLE"
        self.policy: str | None = None
        self.operator_priority = False
        self.operator_active = False
        self.call_started = False
        self.indicated = False
        self.prompt_required = False

    def apply_policy(self, policy: str | None) -> None:
        if not policy:
            self.policy = None
            self.indicated = False
            self.prompt_required = False
            if self.operator_active or self.state == "USER_CALLING":
                return
            if self.state in self.POLICIES:
                self.state = "RETURN_TO_FLOW"
                self.operator_priority = False
            elif self.state == "RETURN_TO_FLOW":
                self.state = "IDLE"
            return
        if policy not in self.POLICIES:
            raise ValueError(f"Policy Call112Service sconosciuta: {policy}")
        self.policy = policy
        if self.operator_active:
            self.state = "OPERATOR_PRIORITY"
            self.operator_priority = True
            self.indicated = True
            self.prompt_required = False
            return
        self.indicated = policy != "CONDITIONAL"
        self.prompt_required = policy == "REQUIRED_PROMPT"
        self.state = policy
        if policy == "OPERATOR_PRIORITY":
            self.operator_priority = True
        elif not self.operator_active:
            self.operator_priority = False

    def handle_event(self, event: str) -> bool:
        if event == EV_CALL112_STARTED:
            self.state = "USER_CALLING"
            self.call_started = True
            self.operator_priority = False
            self.indicated = True
            return True
        if event == EV_OPERATOR_ACTIVE:
            self.state = "OPERATOR_PRIORITY"
            self.operator_priority = True
            self.operator_active = True
            self.call_started = True
            self.indicated = True
            return True
        if event == EV_OPERATOR_ENDED:
            self.state = "RETURN_TO_FLOW"
            self.operator_priority = False
            self.operator_active = False
            self.indicated = False
            self.prompt_required = False
            return True
        return False

    def restore(self, snapshot: dict[str, Any]) -> None:
        self.state = str(snapshot.get("state", "IDLE"))
        self.policy = snapshot.get("policy")
        self.operator_priority = bool(snapshot.get("operator_priority", False))
        self.operator_active = bool(snapshot.get("operator_active", False))
        self.call_started = bool(
            snapshot.get(
                "call_started",
                self.operator_active or self.state in {"USER_CALLING", "OPERATOR_PRIORITY"},
            )
        )
        self.indicated = bool(
            snapshot.get(
                "indicated",
                self.state not in {"IDLE", "CONDITIONAL", "RETURN_TO_FLOW"},
            )
        )
        self.prompt_required = bool(
            snapshot.get("prompt_required", self.policy == "REQUIRED_PROMPT")
        )

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "state": self.state,
                "policy": self.policy,
                "operator_priority": self.operator_priority,
                "operator_active": self.operator_active,
                "call_started": self.call_started,
                "indicated": self.indicated,
                "prompt_required": self.prompt_required,
                "manual_call_only": True,
            }
        )
