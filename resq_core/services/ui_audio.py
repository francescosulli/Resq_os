from __future__ import annotations

import copy
from typing import Any

from hardware.audio import AudioGuide


class UIAudioService:
    def __init__(self, audio: AudioGuide) -> None:
        self.audio = audio
        self.reset()

    def reset(self) -> None:
        self.state = "WAITING_INPUT"
        self.last_prompt = ""
        self.metronome_active = False
        self.operator_active = False
        self.voice_suppressed = False
        self.metronome_ducked = False
        self.playback_sequence = 0
        self.playback_command = "STOP"

    def render(self, node: dict[str, Any], *, operator_active: bool = False) -> None:
        self.audio.stop_instruction()
        self.state = "RENDERING"
        self.last_prompt = str(node.get("prompt", ""))
        self.metronome_active = bool(node.get("metronome", False))
        self.operator_active = bool(operator_active)
        self.voice_suppressed = self.operator_active
        self.metronome_ducked = self.operator_active and self.metronome_active
        self.playback_sequence += 1
        if self.voice_suppressed:
            self.state = "VOICE_SUPPRESSED"
            self.playback_command = "SUSPEND"
            return
        self.state = "PLAYING_AUDIO"
        self.playback_command = "SPEAK"
        self.audio.play_instruction(self.last_prompt)
        self.state = "WAITING_INPUT"

    def repeat(self) -> None:
        if self.last_prompt and not self.voice_suppressed:
            self.state = "PLAYING_AUDIO"
            self.playback_sequence += 1
            self.playback_command = "SPEAK"
            self.audio.play_instruction(self.last_prompt)
            self.state = "WAITING_INPUT"

    def set_operator_active(self, active: bool) -> None:
        previous = self.operator_active
        self.operator_active = bool(active)
        self.voice_suppressed = self.operator_active
        self.metronome_ducked = self.operator_active and self.metronome_active
        if self.voice_suppressed:
            self.audio.stop_instruction()
            self.state = "VOICE_SUPPRESSED"
            self.playback_sequence += 1
            self.playback_command = "SUSPEND"
        elif self.state == "VOICE_SUPPRESSED":
            self.state = "WAITING_INPUT"
            if previous:
                self.playback_sequence += 1
                self.playback_command = "STOP"

    def restore(self, snapshot: dict[str, Any]) -> None:
        self.state = str(snapshot.get("state", "WAITING_INPUT"))
        self.last_prompt = str(snapshot.get("last_prompt", ""))
        self.metronome_active = bool(snapshot.get("metronome_active", False))
        self.operator_active = bool(snapshot.get("operator_active", False))
        self.voice_suppressed = bool(
            snapshot.get("voice_suppressed", self.operator_active)
        )
        self.metronome_ducked = bool(
            snapshot.get(
                "metronome_ducked",
                self.operator_active and self.metronome_active,
            )
        )
        self.playback_sequence = int(snapshot.get("playback_sequence", 0))
        self.playback_command = str(snapshot.get("playback_command", "STOP"))

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "state": self.state,
                "last_prompt": self.last_prompt,
                "metronome_active": self.metronome_active,
                "operator_active": self.operator_active,
                "voice_suppressed": self.voice_suppressed,
                "metronome_ducked": self.metronome_ducked,
                "playback_sequence": self.playback_sequence,
                "playback_command": self.playback_command,
            }
        )
