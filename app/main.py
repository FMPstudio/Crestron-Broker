from __future__ import annotations

import argparse
import asyncio
import logging

import urllib3

from app.broker_service import BrokerService
from app.config import load_config
from app.logging_setup import configure_logging
from app.payload_manager import PayloadManager
from app.state_store import StateStore
from app.tcp_server import BrokerTCPServer
from app.websocket_server import BrokerWebSocketServer


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crestron-Matrox routing broker")
    parser.add_argument("--config", default="config/config.yaml", help="Path to YAML config")
    parser.add_argument("--dry-run", action="store_true", help="Override config and disable POST calls")
    parser.add_argument(
        "--transport",
        choices=("websocket", "tcp", "both"),
        default="websocket",
        help="Transport server mode to run",
    )
    return parser


async def _run_async(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    if args.dry_run:
        config.dry_run = True

    configure_logging(config.logging_level)
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    payload_manager = PayloadManager(config.payload_directory)
    payload_manager.load()

    state_store = StateStore(config.state_file)
    broker = BrokerService(config=config, payload_manager=payload_manager, state_store=state_store)

    try:
        try:
            await asyncio.to_thread(broker.startup_sync)
        except Exception:
            logging.getLogger("broker").exception(
                "Startup sync failed unexpectedly. Continuing with broker startup in degraded mode."
            )
        tasks: list[asyncio.Task] = []
        if args.transport in ("websocket", "both"):
            ws_server = BrokerWebSocketServer(broker, host=config.bind_host, port=config.websocket_port)
            tasks.append(asyncio.create_task(ws_server.run()))
        if args.transport in ("tcp", "both"):
            tcp_server = BrokerTCPServer(broker, host=config.bind_host, port=config.tcp_port)
            tasks.append(asyncio.create_task(tcp_server.run()))

        await asyncio.gather(*tasks)
    finally:
        broker.close()


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    asyncio.run(_run_async(args))


if __name__ == "__main__":
    main()
