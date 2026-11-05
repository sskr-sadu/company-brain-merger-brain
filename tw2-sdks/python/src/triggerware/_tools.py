from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

import tw2_jsonrpc as rpc

from ._configuration import Authorization


ToolRuntime = Literal["lua", "python", "node"]


class ToolParameter(TypedDict):
    name: str
    type: str


class ToolMetadata(TypedDict):
    description: str
    signature: list[ToolParameter]
    config_schema: NotRequired[dict[str, Any]]


class ToolConnector(TypedDict):
    name: str
    tag: NotRequired[str]


class Tool(TypedDict):
    name: str
    prompt: NotRequired[str]
    meta: ToolMetadata
    code: str
    runtime: ToolRuntime
    connector: NotRequired[ToolConnector]
    configured: bool


class ToolsService:
    def __init__(self, peer: rpc.Peer):
        self._peer = peer

    async def create(
        self,
        name: str | None = None,
        *,
        prompt: str | None = None,
        code: str | None = None,
        meta: ToolMetadata | None = None,
        runtime: ToolRuntime | None = None,
    ) -> Tool:
        if prompt is None and (name is None or code is None or meta is None):
            raise ValueError("name, code, and meta are required without a prompt")
        return await self._peer.call(
            "tools.create",
            _tool_params(name=name, prompt=prompt, code=code, meta=meta, runtime=runtime),
        )

    async def get(self, name: str | list[str]) -> Tool | list[Tool]:
        response = await self._peer.call("tools.get", {"name": name})
        return response["tools"] if isinstance(name, list) else response

    async def update(
        self,
        name: str,
        *,
        prompt: str | None = None,
        code: str | None = None,
        meta: ToolMetadata | None = None,
        runtime: ToolRuntime | None = None,
    ) -> Tool:
        return await self._peer.call(
            "tools.update",
            _tool_params(name=name, prompt=prompt, code=code, meta=meta, runtime=runtime),
        )

    async def list(self) -> list[str]:
        response = await self._peer.call("tools.list")
        return response["tools"]

    async def delete(self, name: str | list[str]) -> None:
        await self._peer.call("tools.delete", {"name": name})

    async def sync(
        self,
        *,
        tools: list[str] | None = None,
        connectors: list[str] | None = None,
    ) -> None:
        await self._peer.call("tools.sync", _tool_params(tools=tools, connectors=connectors))

    async def configure(
        self,
        name: str,
        config: dict[str, Any] | None = None,
        *,
        secure: bool = False,
    ) -> Authorization:
        return await self._peer.call(
            "tools.configure",
            _tool_params(name=name, config=config, secure=secure),
        )


def _tool_params(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}
