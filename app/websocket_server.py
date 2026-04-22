from __future__ import annotations

import asyncio
import logging

from websockets.server import WebSocketServerProtocol, serve

from app.broker_service import BrokerService, CommandError


class BrokerWebSocketServer:
    def __init__(self, broker: BrokerService, host: str, port: int) -> None:
        self.broker = broker
        self.host = host
        self.port = port
        self.log = logging.getLogger("websocket")

    async def run(self) -> None:
        async with serve(self._handler, self.host, self.port):
            self.log.info("WebSocket server listening on ws://%s:%s", self.host, self.port)
            await asyncio.Future()

    async def _handler(self, websocket: WebSocketServerProtocol) -> None:
        async for raw in websocket:
            try:
                command = self.broker.parse_command(raw)
                ack = await asyncio.to_thread(self.broker.route, command)
                await websocket.send(ack)
            except CommandError as exc:
                await websocket.send(str(exc))
            except Exception:
                self.log.exception("Unhandled routing error")
                await websocket.send("ERROR route failed")
