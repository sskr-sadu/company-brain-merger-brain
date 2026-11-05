import tw2_jsonrpc as rpc
from typing import TypedDict

class Health(TypedDict):
    status: str


class SystemUpdate(TypedDict):
    runtimes: list[str]
    connector: str
    artifact: str
    restart_required: bool


class SystemService:
    def __init__(self, peer: rpc.Peer):
        self._peer = peer

    async def health(self) -> Health:
        return await self._peer.call("system.health")

    async def update(self) -> SystemUpdate:
        return await self._peer.call("system.update")

    async def authorize(self, api_key: str) -> bool:
        return (await self._peer.call("system.authorize", {"api_key": api_key}))["ok"]

    async def authorized(self) -> bool:
        return (await self._peer.call("system.authorized"))["ok"]
