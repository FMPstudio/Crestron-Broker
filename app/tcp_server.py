from __future__ import annotations

import asyncio
import logging

from app.broker_service import BrokerService, CommandError


class BrokerTCPServer:
    def __init__(self, broker: BrokerService, host: str, port: int) -> None:
        self.broker = broker
        self.host = host
        self.port = port
        self.log = logging.getLogger("tcp")

    async def run(self) -> None:
        server = await asyncio.start_server(self._handler, self.host, self.port)
        self.log.info("TCP server listening on %s:%s", self.host, self.port)
        async with server:
            await server.serve_forever()

    async def _handler(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        self.log.info("TCP client connected: %s", peer)
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break

                text = raw.decode("utf-8", errors="ignore").strip()
                if not text:
                    continue

                try:
                    command = self.broker.parse_command(text)
                    reply = await asyncio.to_thread(self.broker.route, command)
                except CommandError as exc:
                    reply = str(exc)
                except Exception:
                    self.log.exception("Unhandled routing error")
                    reply = "ERROR route failed"

                writer.write((reply + "\n").encode("utf-8"))
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            self.log.info("TCP client disconnected: %s", peer)
