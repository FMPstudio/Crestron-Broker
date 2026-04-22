from __future__ import annotations

import argparse
import asyncio

from websockets.client import connect


async def run(uri: str, commands: list[str]) -> None:
    async with connect(uri) as ws:
        for command in commands:
            print(f">>> {command}")
            await ws.send(command)
            reply = await ws.recv()
            print(f"<<< {reply}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple WebSocket test client for Crestron broker")
    parser.add_argument("--uri", default="ws://127.0.0.1:8080", help="Broker websocket URI")
    parser.add_argument(
        "commands",
        nargs="*",
        default=["1,7", "1,6", "3,7"],
        help="Commands to send",
    )
    args = parser.parse_args()
    asyncio.run(run(args.uri, args.commands))


if __name__ == "__main__":
    main()
