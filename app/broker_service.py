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
        live_state = BrokerState()
        failed_devices: list[str] = []

        for device_id, client in self.clients.items():
            try:
                client.login()
                snapshot = client.get_stream_snapshot()
                live_state.devices[device_id] = DeviceRuntimeState(
                    video_stream=snapshot["video_stream"],
                    audio_stream=snapshot["audio_stream"],
                    video_manual=snapshot["video_manual"],
                    audio_manual=snapshot["audio_manual"],
                )
                self.log.info("Startup sync succeeded for device=%s", device_id)
            except Exception as exc:
                failed_devices.append(device_id)
                self.log.warning("Startup sync failed for device=%s: %s", device_id, exc)

        if not live_state.devices:
            self.log.warning(
                "Startup sync could not reach any device. "
                "Broker will continue in degraded mode using cached state. "
                "failed_devices=%s",
                failed_devices,
            )
            return

        reconstructed = self._reconstruct_input_map(live_state)
        self.state.devices.update(live_state.devices)
        self.state.input_to_device.update(reconstructed)
        self.state.touch_sync_timestamp()
        self.state_store.save(self.state)
        self.log.info(
            "Synchronization completed with partial/live data. reachable=%s unreachable=%s input_to_device=%s",
            list(live_state.devices.keys()),
            failed_devices,
            self.state.input_to_device,
        )

    def reset_all_streams(self) -> None:
        self.log.info("Reset flag detected: disabling all configured device streams before startup sync")
        for device_id, client in self.clients.items():
            self.log.info("Resetting streams for device=%s", device_id)
            try:
                client.login()
            except Exception as exc:
                self.log.warning("Startup reset login failed for device=%s: %s", device_id, exc)
                continue

            try:
                self.log.info("Applying video disable during startup reset for device=%s", device_id)
                client.apply_video_stream(self.payloads.video_disable)
            except Exception as exc:
                self.log.warning("Startup reset video disable failed for device=%s: %s", device_id, exc)

            try:
                self.log.info("Applying audio disable during startup reset for device=%s", device_id)
                client.apply_audio_stream(self.payloads.audio_disable)
            except Exception as exc:
                self.log.warning("Startup reset audio disable failed for device=%s: %s", device_id, exc)

    def route(self, cmd: Command) -> str:
        input_key = str(cmd.input_id)
        old_device = self.state.input_to_device.get(input_key)
        previous_inputs_for_target = [
            existing_input
            for existing_input, device_id in self.state.input_to_device.items()
            if device_id == cmd.device_id and existing_input != input_key
        ]

        self.log.info("Routing input=%s to device=%s (old=%s)", cmd.input_id, cmd.device_id, old_device)

        for existing_input in previous_inputs_for_target:
            self.state.input_to_device.pop(existing_input, None)
            self.log.info(
                "Cleared previous mapping for target device=%s from input=%s",
                cmd.device_id,
                existing_input,
            )

        if old_device == cmd.device_id:
            if previous_inputs_for_target:
                self.state.touch_sync_timestamp()
                self.state_store.save(self.state)
            return f"{cmd.input_id},{int(cmd.device_id)} OK!"

        if old_device and old_device in self.clients:
            old_client = self.clients[old_device]
            self.log.info("Disabling streams on old device=%s", old_device)
            old_client.apply_video_stream(self.payloads.video_disable)
            old_client.apply_audio_stream(self.payloads.audio_disable)

            previous_old_state = self.state.devices.get(old_device)
            if previous_old_state is not None:
                old_video_stream = dict(previous_old_state.video_stream)
                old_audio_stream = dict(previous_old_state.audio_stream)
                old_video_manual = dict(previous_old_state.video_manual)
                old_audio_manual = dict(previous_old_state.audio_manual)
            else:
                old_video_stream = dict(self.payloads.video_disable)
                old_audio_stream = dict(self.payloads.audio_disable)
                old_video_manual = {}
                old_audio_manual = {}

            old_video_stream["enable"] = False
            old_audio_stream["enable"] = False

            self.state.devices[old_device] = DeviceRuntimeState(
                video_stream=old_video_stream,
                audio_stream=old_audio_stream,
                video_manual=old_video_manual,
                audio_manual=old_audio_manual,
            )
            self.log.info("Updated cached runtime state for old device=%s to disabled", old_device)

        target_client = self.clients[cmd.device_id]
        self.log.info("Applying manual routes on target device=%s", cmd.device_id)
        target_client.apply_video_manual(self.payloads.video_by_input[cmd.input_id])
        target_client.apply_audio_manual(self.payloads.audio_by_input[cmd.input_id])

        self.log.info("Enabling streams on target device=%s", cmd.device_id)
        target_client.apply_video_stream(self.payloads.video_enable)
        target_client.apply_audio_stream(self.payloads.audio_enable)

        self.state.devices[cmd.device_id] = DeviceRuntimeState(
            video_stream=dict(self.payloads.video_enable),
            audio_stream=dict(self.payloads.audio_enable),
            video_manual=dict(self.payloads.video_by_input[cmd.input_id]),
            audio_manual=dict(self.payloads.audio_by_input[cmd.input_id]),
        )
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
