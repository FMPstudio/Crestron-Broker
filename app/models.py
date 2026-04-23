from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class DeviceConfig:
    device_id: str
    ip: str


@dataclass(slots=True)
class RetryConfig:
    attempts: int
    backoff_seconds: float


@dataclass(slots=True)
class BrokerConfig:
    bind_host: str
    websocket_port: int
    tcp_port: int
    websocket_path: str
    username: str
    password: str
    payload_directory: str
    state_file: str
    request_timeout_seconds: float
    retry: RetryConfig
    logging_level: str
    dry_run: bool
    devices: list[DeviceConfig]


@dataclass(slots=True)
class Command:
    input_id: int
    device_id: str


@dataclass(slots=True)
class DeviceRuntimeState:
    video_stream: dict[str, Any] = field(default_factory=dict)
    audio_stream: dict[str, Any] = field(default_factory=dict)
    video_manual: dict[str, Any] = field(default_factory=dict)
    audio_manual: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BrokerState:
    input_to_device: dict[str, str] = field(default_factory=dict)
    devices: dict[str, DeviceRuntimeState] = field(default_factory=dict)
    last_successful_sync: str | None = None

    def touch_sync_timestamp(self) -> None:
        self.last_successful_sync = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
