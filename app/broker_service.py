from __future__ import annotations

import logging
from typing import Iterable

from app.matrox_client import MatroxClient
from app.models import BrokerConfig, BrokerState, Command, DeviceRuntimeState
from app.payload_manager import PayloadManager
from app.state_store import StateStore


class CommandError(RuntimeError):
    pass


class BrokerService:
    def __init__(
        self,
        config: BrokerConfig,
        payload_manager: PayloadManager,
        state_store: StateStore,
    ) -> None:
        self.config = config
        self.payloads = payload_manager
        self.state_store = state_store
        self.log = logging.getLogger("broker")

        self.clients: dict[str, MatroxClient] = {}
        self.state = self.state_store.load()

        for device in config.devices:
            self.clients[device.device_id] = MatroxClient(
                ip=device.ip,
                username=config.username,
                password=config.password,
                timeout_seconds=config.request_timeout_seconds,
                retry_attempts=config.retry.attempts,
                backoff_seconds=config.retry.backoff_seconds,
                dry_run=config.dry_run,
            )

    def close(self) -> None:
        for client in self.clients.values():
            client.close()

    def parse_command(self, raw: str) -> Command:
        cleaned = raw.strip()
        parts = [x.strip() for x in cleaned.split(",")]
        if len(parts) != 2:
            raise CommandError("ERROR invalid command format")

        try:
            input_id = int(parts[0])
        except ValueError as exc:
            raise CommandError("ERROR invalid input") from exc

        device_raw = parts[1]
        try:
            device_id = str(int(device_raw)).zfill(2)
        except ValueError as exc:
            raise CommandError("ERROR unknown device") from exc

        if input_id not in (1, 2, 3, 4):
            raise CommandError("ERROR invalid input")
        if device_id not in self.clients:
            raise CommandError("ERROR unknown device")

        return Command(input_id=input_id, device_id=device_id)

    def startup_sync(self) -> None:
        self.log.info("Starting device synchronization")
        new_state = BrokerState()
        for device_id, client in self.clients.items():
            client.login()
            snapshot = client.get_stream_snapshot()
            new_state.devices[device_id] = DeviceRuntimeState(
                video_stream=snapshot["video_stream"],
                audio_stream=snapshot["audio_stream"],
                video_manual=snapshot["video_manual"],
                audio_manual=snapshot["audio_manual"],
            )

        reconstructed = self._reconstruct_input_map(new_state)
        new_state.input_to_device = reconstructed
        new_state.touch_sync_timestamp()
        self.state = new_state
        self.state_store.save(self.state)
        self.log.info("Synchronization completed. input_to_device=%s", reconstructed)

    def route(self, cmd: Command) -> str:
        input_key = str(cmd.input_id)
        old_device = self.state.input_to_device.get(input_key)

        self.log.info("Routing input=%s to device=%s (old=%s)", cmd.input_id, cmd.device_id, old_device)

        if old_device == cmd.device_id:
            return f"{cmd.input_id},{int(cmd.device_id)} OK!"

        if old_device and old_device in self.clients:
            old_client = self.clients[old_device]
            self.log.info("Disabling streams on old device=%s", old_device)
            old_client.apply_video_stream(self.payloads.video_disable)
            old_client.apply_audio_stream(self.payloads.audio_disable)

        target_client = self.clients[cmd.device_id]
        self.log.info("Applying manual routes on target device=%s", cmd.device_id)
        target_client.apply_video_manual(self.payloads.video_by_input[cmd.input_id])
        target_client.apply_audio_manual(self.payloads.audio_by_input[cmd.input_id])

        self.log.info("Enabling streams on target device=%s", cmd.device_id)
        target_client.apply_video_stream(self.payloads.video_enable)
        target_client.apply_audio_stream(self.payloads.audio_enable)

        self.state.input_to_device[input_key] = cmd.device_id
        self.state.touch_sync_timestamp()
        self.state_store.save(self.state)
        return f"{cmd.input_id},{int(cmd.device_id)} OK!"

    def _reconstruct_input_map(self, state: BrokerState) -> dict[str, str]:
        mapping: dict[str, str] = {}

        for device_id, device_state in state.devices.items():
            video_enabled = bool(device_state.video_stream.get("enable", False))
            audio_enabled = bool(device_state.audio_stream.get("enable", False))

            if not (video_enabled and audio_enabled):
                continue

            video_dst = str(device_state.video_manual.get("dstIpAddress", ""))
            audio_dst = str(device_state.audio_manual.get("dstIpAddress", ""))

            video_input = self.payloads.video_dest_to_input.get(video_dst)
            audio_input = self.payloads.audio_dest_to_input.get(audio_dst)
            if video_input and audio_input and video_input == audio_input:
                mapping[str(video_input)] = device_id

        return mapping

    @property
    def known_device_ids(self) -> Iterable[str]:
        return self.clients.keys()
