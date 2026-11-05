from __future__ import annotations

from typing import Any, NotRequired, TypedDict

import tw2_jsonrpc as rpc


class AgentMetadata(TypedDict):
    description: str
    tools: NotRequired[list[str]]
    mcp_servers: NotRequired[list[list[str]]]
    triggers: NotRequired[list[str]]
    output_schema: NotRequired[dict[str, Any]]


class Agent(TypedDict):
    name: str
    prompt: NotRequired[str]
    meta: AgentMetadata
    instructions: str


class AgentsService:
    def __init__(self, peer: rpc.Peer):
        self._peer = peer

    async def create(
        self,
        name: str | None = None,
        *,
        prompt: str | None = None,
        meta: AgentMetadata | None = None,
        instructions: str | None = None,
    ) -> Agent:
        if prompt is None and (name is None or meta is None or instructions is None):
            raise ValueError("name, meta, and instructions are required without a prompt")
        return await self._peer.call(
            "agents.create",
            _agent_params(name=name, prompt=prompt, meta=meta, instructions=instructions),
        )

    async def get(self, name: str | list[str]) -> Agent | list[Agent]:
        response = await self._peer.call("agents.get", {"name": name})
        return response["agents"] if isinstance(name, list) else response

    async def update(
        self,
        name: str,
        *,
        prompt: str | None = None,
        meta: AgentMetadata | None = None,
        instructions: str | None = None,
    ) -> Agent:
        return await self._peer.call(
            "agents.update",
            _agent_params(name=name, prompt=prompt, meta=meta, instructions=instructions),
        )

    async def list(self) -> list[str]:
        response = await self._peer.call("agents.list")
        return response["agents"]

    async def delete(self, name: str | list[str]) -> None:
        await self._peer.call("agents.delete", {"name": name})

    async def run(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self._peer.call("agents.run", {"name": name, "data": data})

    async def sync(
        self,
        *,
        agents: list[str] | None = None,
        connectors: list[str] | None = None,
    ) -> None:
        await self._peer.call(
            "agents.sync",
            _agent_params(agents=agents, connectors=connectors),
        )


def _agent_params(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}
