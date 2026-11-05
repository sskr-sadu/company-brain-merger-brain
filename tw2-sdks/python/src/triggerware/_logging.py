from __future__ import annotations

from typing import Literal

import tw2_jsonrpc as rpc


LogLevel = Literal["debug", "info", "error"]


class LoggingService:
    def __init__(self, peer: rpc.Peer):
        self._peer = peer

    async def set(self, level: LogLevel) -> None:
        await self._peer.call("logging.set", {"level": level})
