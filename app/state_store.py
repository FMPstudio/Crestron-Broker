from __future__ import annotations

import json
from pathlib import Path

from app.models import BrokerState, DeviceRuntimeState


class StateStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def load(self) -> BrokerState:
        if not self._path.exists():
            return BrokerState()

        with self._path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        devices: dict[str, DeviceRuntimeState] = {}
        for device_id, payload in raw.get("devices", {}).items():
            devices[device_id] = DeviceRuntimeState(
                video_stream=payload.get("video_stream", {}),
                audio_stream=payload.get("audio_stream", {}),
                video_manual=payload.get("video_manual", {}),
                audio_manual=payload.get("audio_manual", {}),
            )

        return BrokerState(
            input_to_device={str(k): str(v) for k, v in raw.get("input_to_device", {}).items()},
            devices=devices,
            last_successful_sync=raw.get("last_successful_sync"),
        )

    def save(self, state: BrokerState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        serialized = {
            "input_to_device": state.input_to_device,
            "devices": {
                device_id: {
                    "video_stream": device_state.video_stream,
                    "audio_stream": device_state.audio_stream,
                    "video_manual": device_state.video_manual,
                    "audio_manual": device_state.audio_manual,
                }
                for device_id, device_state in state.devices.items()
            },
            "last_successful_sync": state.last_successful_sync,
        }

        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(serialized, handle, indent=2, sort_keys=True)
