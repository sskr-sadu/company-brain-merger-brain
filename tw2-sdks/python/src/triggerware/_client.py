from __future__ import annotations

from typing import Any, Self

import tw2_jsonrpc as rpc

from ._configuration import ConfigurationService
from ._tables import TablesService
from ._cursors import CursorsService
from ._connectors import ConnectorsService
from ._logging import LoggingService
from ._agents import AgentsService
from ._tools import ToolsService
from ._queries import QueriesService
from ._runtimes import RuntimesService
from ._system import SystemService
from ._triggers import TriggersService


class TriggerwareClient:

    def __init__(self, peer: rpc.Peer) -> None:
        self._peer = peer
        self.configuration = ConfigurationService(peer)
        self.tables = TablesService(peer)
        self.cursors = CursorsService(peer)
        self.connectors = ConnectorsService(peer)
        self.logging = LoggingService(peer)
        self.agents = AgentsService(peer)
        self.tools = ToolsService(peer)
        self.queries = QueriesService(peer)
        self.runtimes = RuntimesService(peer)
        self.system = SystemService(peer)
        self.triggers = TriggersService(peer)

    async def mcp(self, method: str, params: dict[str, Any] | None = None) -> Any:
        request: dict[str, Any] = {"method": method}
        if params is not None:
            request["params"] = params
        return await self._peer.call("mcp", request)

    @classmethod
    async def connect_tcp(cls, address: str) -> Self:
        host, port_text = address.rsplit(":", 1)
        peer = await rpc.connect_tcp(host, int(port_text))
        return cls(peer)

    @classmethod
    async def connect_ws(cls, url: str, api_key: str) -> Self:
        peer = await rpc.connect_ws(url)
        client = cls(peer)
        await client.system.authorize(api_key)
        return client
