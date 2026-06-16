from __future__ import annotations

from typing import Any

from hardware.audio import AudioGuide
from hardware.leds import LEDController
from hardware.nfc import NFCReader
from resq_core.logger import get_logger
from resq_core.state_manager import StateManager


class FlowError(ValueError):
    """Raised when the user action is not valid for the current flow state."""


class EmergencyFlow:
    def __init__(
        self,
        protocols: dict[str, dict[str, Any]],
        state: StateManager,
        leds: LEDController,
        nfc: NFCReader,
        audio: AudioGuide,
    ) -> None:
        self.protocols = protocols
        self.state = state
        self.leds = leds
        self.nfc = nfc
        self.audio = audio
        self.logger = get_logger("flow")

    def start_emergency(self) -> dict[str, Any]:
        self.logger.info("Avvio emergenza: selezione protocollo")
        self.state.start_emergency()
        return self.public_state()

    def start_protocol(self, protocol_id: str) -> dict[str, Any]:
        protocol = self._get_protocol(protocol_id)
        first_step = protocol["first_step"]
        self.state.start_protocol(protocol_id, first_step)
        self.logger.info("Avvio protocollo: %s", protocol["title"])
        self._enter_step(protocol, self._get_step(protocol, first_step))
        return self.public_state()

    def answer(self, answer: str) -> dict[str, Any]:
        answer = answer.lower()
        if answer not in {"yes", "no"}:
            raise FlowError("Risposta non valida")

        protocol, step = self._current_protocol_and_step()
        if step["type"] != "question":
            raise FlowError("Questo step non richiede una risposta si/no")

        target = step["answers"][answer]
        question = step.get("question", step["instruction"])
        self.state.record_answer(question, answer)
        self.logger.info("Risposta utente: %s -> %s", question, answer)
        self._goto(protocol, target)
        return self.public_state()

    def next_step(self) -> dict[str, Any]:
        protocol, step = self._current_protocol_and_step()
        if step["type"] == "question":
            raise FlowError("Rispondi si' o no per continuare")

        if step["type"] == "item":
            nfc_status = self.state.snapshot()["nfc_status"]["status"]
            if nfc_status != "confirmed":
                raise FlowError("Simula la lettura NFC prima di continuare")

        target = step.get("next")
        if not target:
            summary = step.get("summary", step["instruction"])
            self.state.complete(summary)
            self.logger.info("Completamento protocollo senza step successivo")
            return self.public_state()

        self._goto(protocol, target)
        return self.public_state()

    def back(self) -> dict[str, Any]:
        previous_step = self.state.back()
        if previous_step is None:
            return self.public_state()

        protocol = self._get_protocol(self.state.snapshot()["protocol_id"])
        self.logger.info("Indietro: torno allo step %s", previous_step)
        self._enter_step(protocol, self._get_step(protocol, previous_step))
        return self.public_state()

    def repeat_audio(self) -> dict[str, Any]:
        protocol, step = self._current_protocol_and_step()
        text = self._step_audio_text(step)
        self.audio.play_instruction(text)
        self.state.set_audio(text)
        self.logger.info("Ripeti audio: %s", text)
        return self.public_state()

    def simulate_nfc(self) -> dict[str, Any]:
        _protocol, step = self._current_protocol_and_step()
        if step["type"] != "item":
            raise FlowError("Nessun presidio richiesto in questo step")

        item = step["item"]
        detected = self.nfc.simulate_read(item["name"])
        self.state.record_nfc(item["name"], detected, True)
        self.state.set_nfc_status(
            "confirmed",
            f"[NFC] Oggetto corretto rilevato: {detected}",
            expected_item=item["name"],
            detected_item=detected,
        )
        self.logger.info("NFC simulato: atteso=%s rilevato=%s", item["name"], detected)
        return self.public_state()

    def reset_home(self) -> dict[str, Any]:
        self.leds.clear()
        self.logger.info("Ritorno alla home")
        self.state.reset_home()
        return self.public_state()

    def run_diagnostic(self, test_name: str) -> dict[str, Any]:
        if test_name == "led":
            message = self.leds.test_sequence()
        elif test_name == "nfc":
            message = self.nfc.test()
        elif test_name == "audio":
            message = self.audio.test()
            self.state.set_audio(message)
        elif test_name == "status":
            message = "App attiva, backend operativo, hardware in simulazione"
        else:
            raise FlowError("Test diagnostico non riconosciuto")

        self.logger.info("Diagnostica %s: %s", test_name, message)
        return {
            "test": test_name,
            "message": message,
            "state": self.public_state(),
        }

    def handle_button(self, button_name: str) -> dict[str, Any]:
        if button_name == "yes":
            return self.answer("yes")
        if button_name == "no":
            return self.answer("no")
        if button_name == "back":
            return self.back()
        if button_name == "repeat_audio":
            return self.repeat_audio()
        if button_name == "home_emergency":
            mode = self.state.snapshot()["mode"]
            if mode == "home":
                return self.start_emergency()
            return self.reset_home()
        raise FlowError("Pulsante non riconosciuto")

    def public_state(self) -> dict[str, Any]:
        snapshot = self.state.snapshot()
        protocol = None
        step = None

        protocol_id = snapshot.get("protocol_id")
        if protocol_id:
            source = self._get_protocol(protocol_id)
            protocol = {
                "id": source["id"],
                "title": source["title"],
                "disclaimer": source.get("disclaimer", ""),
            }
            if snapshot.get("current_step_id"):
                step = self._public_step(
                    self._get_step(source, snapshot["current_step_id"])
                )

        return {
            "mode": snapshot["mode"],
            "protocol": protocol,
            "step": step,
            "answers": snapshot["answers"],
            "requested_items": snapshot["requested_items"],
            "nfc_events": snapshot["nfc_events"],
            "started_at": snapshot["started_at"],
            "completed_at": snapshot["completed_at"],
            "last_audio_text": snapshot["last_audio_text"],
            "active_item": snapshot["active_item"],
            "last_answer_message": snapshot["last_answer_message"],
            "summary": snapshot["summary"],
            "led_status": snapshot["led_status"],
            "nfc_status": snapshot["nfc_status"],
        }

    def _goto(self, protocol: dict[str, Any], step_id: str) -> None:
        self.state.transition_to(step_id)
        self._enter_step(protocol, self._get_step(protocol, step_id))

    def _enter_step(self, protocol: dict[str, Any], step: dict[str, Any]) -> None:
        text = self._step_audio_text(step)
        self.audio.play_instruction(text)
        self.state.set_audio(text)

        if step["type"] == "item":
            item = step["item"]
            led_message = self.leds.highlight_compartment(item["compartment"])
            self.state.set_active_item(item)
            self.state.record_item_requested(item)
            self.state.set_led_status(True, item["compartment"], led_message)
            self.state.set_nfc_status(
                "waiting",
                f"[NFC] In attesa di: {item['name']}",
                expected_item=item["name"],
            )
            self.logger.info(
                "Presidio richiesto: %s, vano: %s",
                item["name"],
                item["compartment"],
            )
        else:
            self.leds.clear()
            self.state.set_led_status(False, "", "[LED] Perimetri spenti")

        if step["type"] == "end":
            summary = step.get("summary", step["instruction"])
            self.state.complete(summary)
            self.logger.info(
                "Completamento protocollo: %s - %s",
                protocol["title"],
                summary,
            )

    def _step_audio_text(self, step: dict[str, Any]) -> str:
        if step["type"] == "question":
            return f"{step['instruction']} {step.get('question', '')}".strip()
        return step["instruction"]

    def _current_protocol_and_step(self) -> tuple[dict[str, Any], dict[str, Any]]:
        snapshot = self.state.snapshot()
        if snapshot["mode"] not in {"protocol", "completed"}:
            raise FlowError("Nessun protocollo attivo")
        protocol = self._get_protocol(snapshot["protocol_id"])
        return protocol, self._get_step(protocol, snapshot["current_step_id"])

    def _get_protocol(self, protocol_id: str) -> dict[str, Any]:
        try:
            return self.protocols[protocol_id]
        except KeyError as exc:
            raise FlowError(f"Protocollo non trovato: {protocol_id}") from exc

    def _get_step(self, protocol: dict[str, Any], step_id: str) -> dict[str, Any]:
        for step in protocol["steps"]:
            if step["id"] == step_id:
                return step
        raise FlowError(f"Step non trovato: {step_id}")

    def _public_step(self, step: dict[str, Any]) -> dict[str, Any]:
        public = {
            "id": step["id"],
            "type": step["type"],
            "instruction": step["instruction"],
            "action_label": step.get("action_label", "Continua"),
        }
        if step["type"] == "question":
            public["question"] = step["question"]
        if step["type"] == "item":
            public["item"] = step["item"]
        if step["type"] == "end":
            public["summary"] = step.get("summary", step["instruction"])
        return public

