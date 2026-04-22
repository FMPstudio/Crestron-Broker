from __future__ import annotations

import json
from pathlib import Path


class PayloadError(RuntimeError):
    pass


class PayloadManager:
    def __init__(self, payload_dir: str) -> None:
        self.payload_dir = Path(payload_dir)
        if not self.payload_dir.exists():
            raise PayloadError(f"Payload directory not found: {payload_dir}")

        self.video_by_input: dict[int, dict] = {}
        self.audio_by_input: dict[int, dict] = {}
        self.video_enable: dict = {}
        self.video_disable: dict = {}
        self.audio_enable: dict = {}
        self.audio_disable: dict = {}

        self.video_dest_to_input: dict[str, int] = {}
        self.audio_dest_to_input: dict[str, int] = {}

    def load(self) -> None:
        for file in self.payload_dir.glob("*.json"):
            payload = json.loads(file.read_text(encoding="utf-8"))
            name = file.name.lower()

            if "multicast_video_stream_enable" in name:
                self.video_enable = payload
            elif "multicast_video_stream_disable" in name:
                self.video_disable = payload
            elif "multicast_audio_stream_enable" in name:
                self.audio_enable = payload
            elif "multicast_audio_stream_disable" in name:
                self.audio_disable = payload
            elif "multicast_video_input_" in name:
                input_id = int(name.split("multicast_video_input_")[1].split(".")[0])
                self.video_by_input[input_id] = payload
                self.video_dest_to_input[str(payload.get("dstIpAddress", ""))] = input_id
            elif "multicast_audio_input_" in name:
                input_id = int(name.split("multicast_audio_input_")[1].split(".")[0])
                self.audio_by_input[input_id] = payload
                self.audio_dest_to_input[str(payload.get("dstIpAddress", ""))] = input_id

        missing = [
            not self.video_enable,
            not self.video_disable,
            not self.audio_enable,
            not self.audio_disable,
            len(self.video_by_input) != 4,
            len(self.audio_by_input) != 4,
        ]
        if any(missing):
            raise PayloadError("Payload set is incomplete. Expected 4 input payloads each for audio/video and stream enable/disable payloads.")
