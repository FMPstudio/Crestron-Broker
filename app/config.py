from __future__ import annotations

from pathlib import Path

import yaml

from app.models import BrokerConfig, DeviceConfig, RetryConfig


class ConfigError(RuntimeError):
    pass


def load_config(config_path: str) -> BrokerConfig:
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Config file does not exist: {config_path}")

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    try:
        retry = RetryConfig(
            attempts=int(raw["retry"]["attempts"]),
            backoff_seconds=float(raw["retry"]["backoff_seconds"]),
        )

        devices = [
            DeviceConfig(device_id=str(item["id"]).zfill(2), ip=str(item["ip"]))
            for item in raw["devices"]
        ]

        return BrokerConfig(
            bind_host=str(raw["bind_host"]),
            websocket_port=int(raw.get("websocket_port", raw.get("bind_port", 8080))),
            tcp_port=int(raw.get("tcp_port", 8081)),
            websocket_path=str(raw.get("websocket_path", "/")),
            username=str(raw["username"]),
            password=str(raw["password"]),
            payload_directory=str(raw["payload_directory"]),
            state_file=str(raw["state_file"]),
            request_timeout_seconds=float(raw.get("request_timeout_seconds", 5.0)),
            retry=retry,
            logging_level=str(raw.get("logging_level", "INFO")),
            dry_run=bool(raw.get("dry_run", False)),
            devices=devices,
        )
    except KeyError as exc:
        raise ConfigError(f"Missing required config key: {exc}") from exc
