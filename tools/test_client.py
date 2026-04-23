from __future__ import annotations

import argparse
import asyncio

from websockets import connect


async def run_websocket(uri: str, commands: list[str]) -> None:
    async with connect(uri) as ws:
        for command in commands:
            print(f">>> {command}")
            await ws.send(command)
            reply = await ws.recv()
            print(f"<<< {reply}")


async def run_tcp(host: str, port: int, commands: list[str]) -> None:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        for command in commands:
            print(f">>> {command}")
            writer.write((command + "\n").encode("utf-8"))
            await writer.drain()
            reply = await reader.readline()
            print(f"<<< {reply.decode('utf-8', errors='ignore').strip()}")
    finally:
        writer.close()
        await writer.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple transport test client for Crestron broker")
    parser.add_argument("--transport", choices=("websocket", "tcp"), default="websocket")
    parser.add_argument("--uri", default="ws://127.0.0.1:8080", help="Broker websocket URI")
    parser.add_argument("--host", default="127.0.0.1", help="Broker TCP host")
    parser.add_argument("--port", type=int, default=8081, help="Broker TCP port")
    parser.add_argument(
        "commands",
        nargs="*",
        default=["1,7", "1,6", "3,7"],
        help="Commands to send",
    )
    args = parser.parse_args()
    if args.transport == "websocket":
        asyncio.run(run_websocket(args.uri, args.commands))
    else:
        asyncio.run(run_tcp(args.host, args.port, args.commands))


if __name__ == "__main__":
    main()
