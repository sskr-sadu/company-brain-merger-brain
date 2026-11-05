from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

import tw2_jsonrpc as rpc

from ._configuration import Authorization


ConnectorRuntime = Literal["python", "node"]


class Connector(TypedDict):
    config: dict[str, Any] | None
    tables: list[str]
    tools: list[str]
    agents: list[str]


class ConnectorDescription(TypedDict):
    description: str
    config_schema: dict[str, Any]
    oauth_provider: NotRequired[str]
    runtime: NotRequired[ConnectorRuntime]
    dependencies: NotRequired[list[str]]
    tables: list[str]
    tools: list[str]
    agents: list[str]


class ConnectorCatalogEntry(TypedDict):
    name: str
    description: str


class ConnectorsService:
    def __init__(self, peer: rpc.Peer):
        self._peer = peer

    async def install(
        self,
        *,
        name: str | None = None,
        url: str | None = None,
        tag: str | None = None,
        config: dict[str, Any] | None = None,
        secure: bool = False,
    ) -> Authorization:
        if name is None and url is None:
            raise ValueError("name or url is required")
        return await self._peer.call(
            "connectors.install",
            _connector_params(name=name, url=url, tag=tag, config=config, secure=secure),
        )

    async def get(
        self, name: str | list[str], *, tag: str | None = None
    ) -> Connector | list[Connector]:
        response = await self._peer.call(
            "connectors.get",
            _connector_params(name=name, tag=tag),
        )
        return response["connectors"] if isinstance(name, list) else response

    async def list(self) -> list[str]:
        response = await self._peer.call("connectors.list")
        return response["connectors"]

    async def configure(
        self,
        name: str,
        *,
        tag: str | None = None,
        config: dict[str, Any] | None = None,
        secure: bool = False,
    ) -> Authorization:
        return await self._peer.call(
            "connectors.configure",
            _connector_params(name=name, tag=tag, config=config, secure=secure),
        )

    async def authorize(self, name: str, *, tag: str | None = None) -> str:
        response = await self._peer.call(
            "connectors.authorize",
            _connector_params(name=name, tag=tag),
        )
        return response["url"]

    async def catalog(self) -> list[ConnectorCatalogEntry]:
        response = await self._peer.call("connectors.catalog")
        return response["connectors"]

    async def describe(
        self,
        *,
        name: str | None = None,
        url: str | None = None,
    ) -> ConnectorDescription:
        if name is None and url is None:
            raise ValueError("name or url is required")
        return await self._peer.call(
            "connectors.describe",
            _connector_params(name=name, url=url),
        )

    async def uninstall(self, name: str | list[str], *, tag: str | None = None) -> None:
        await self._peer.call(
            "connectors.uninstall",
            _connector_params(name=name, tag=tag),
        )


def _connector_params(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}
