from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

import tw2_jsonrpc as rpc

from ._configuration import Authorization


TableRuntime = Literal["lua", "python", "node"]


class TableColumn(TypedDict):
    name: str
    type: str


class TableGenerator(TypedDict):
    name: str
    inputs: list[str]


class TableMetadata(TypedDict):
    description: str
    columns: list[TableColumn]
    generators: list[TableGenerator]
    config_schema: NotRequired[dict[str, Any]]


class TableConnector(TypedDict):
    name: str
    tag: NotRequired[str]


class Table(TypedDict):
    name: str
    prompt: NotRequired[str]
    meta: TableMetadata
    code: str
    runtime: TableRuntime
    connector: NotRequired[TableConnector]
    configured: bool


class TablesService:
    def __init__(self, peer: rpc.Peer):
        self._peer = peer

    async def create(
        self,
        name: str | None = None,
        *,
        prompt: str | None = None,
        code: str | None = None,
        meta: TableMetadata | None = None,
        runtime: TableRuntime | None = None,
    ) -> Table:
        if prompt is None and (name is None or code is None or meta is None):
            raise ValueError("name, code, and meta are required without a prompt")
        table = await self._peer.call(
            "tables.create",
            self._definition_params(
                name=name,
                prompt=prompt,
                code=code,
                meta=meta,
                runtime=runtime,
            ),
        )
        return table

    async def get(self, name: str | list[str]) -> Table | list[Table]:
        response = await self._peer.call("tables.get", {"name": name})
        return response["tables"] if isinstance(name, list) else response

    async def update(
        self,
        name: str,
        *,
        prompt: str | None = None,
        code: str | None = None,
        meta: TableMetadata | None = None,
        runtime: TableRuntime | None = None,
    ) -> Table:
        table = await self._peer.call(
            "tables.update",
            self._definition_params(
                name=name,
                prompt=prompt,
                code=code,
                meta=meta,
                runtime=runtime,
            ),
        )
        return table

    async def list(self) -> list[str]:
        response = await self._peer.call("tables.list")
        return response["tables"]

    async def delete(self, name: str | list[str]) -> None:
        await self._peer.call("tables.delete", {"name": name})

    async def sync(
        self,
        *,
        tables: list[str] | None = None,
        connectors: list[str] | None = None,
    ) -> None:
        params = {
            "tables": tables,
            "connectors": connectors,
        }
        await self._peer.call(
            "tables.sync",
            {key: value for key, value in params.items() if value is not None},
        )

    async def configure(
        self,
        name: str,
        config: dict[str, Any] | None = None,
        *,
        secure: bool = False,
    ) -> Authorization:
        params = {"name": name, "config": config, "secure": secure}
        return await self._peer.call(
            "tables.configure",
            {key: value for key, value in params.items() if value is not None},
        )

    def _definition_params(
        self,
        *,
        name: str | None,
        prompt: str | None,
        code: str | None,
        meta: TableMetadata | None,
        runtime: TableRuntime | None,
    ) -> dict[str, Any]:
        params = {
            "name": name,
            "prompt": prompt,
            "code": code,
            "meta": meta,
            "runtime": runtime,
        }
        return {key: value for key, value in params.items() if value is not None}
