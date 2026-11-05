from __future__ import annotations

from typing import Any, NotRequired, TypedDict

import tw2_jsonrpc as rpc


class QuerySignature(TypedDict):
    name: str
    type: str


class QueryParameter(TypedDict):
    name: str
    type: str


class QueryParameterValue(TypedDict):
    name: str
    value: Any


class QueryDefinition(TypedDict):
    name: str
    description: str
    sql: NotRequired[str]
    prompt: NotRequired[str]
    batch_size: NotRequired[int]
    timeout_ms: NotRequired[int]
    params: NotRequired[list[QueryParameter]]
    signature: list[QuerySignature]


class QueryFetch(TypedDict):
    rows: list[list[Any]]
    exhausted: bool


class Query:
    def __init__(self, peer: rpc.Peer, definition: QueryDefinition):
        self._peer = peer
        self._replace(definition)

    async def reset(self) -> None:
        definition: QueryDefinition = await self._peer.call(
            "queries.reset",
            {"name": self.name},
        )
        self._replace(definition)

    async def fetch(
        self,
        *,
        params: list[QueryParameterValue] | None = None,
        rows: int | None = None,
    ) -> list[list[Any]]:
        if self.exhausted:
            return []

        if params is not None:
            self._fetch_params = params
        if rows is not None:
            self._fetch_rows = rows
        response: QueryFetch = await self._peer.call(
            "queries.fetch",
            _query_params(name=self.name, params=self._fetch_params, rows=self._fetch_rows),
        )
        self.exhausted = response["exhausted"]
        self._cache.extend(response["rows"])
        return response["rows"]

    def __aiter__(self) -> Query:
        return self

    async def __anext__(self) -> list[Any]:
        if self._cache_position < len(self._cache):
            row = self._cache[self._cache_position]
            self._cache_position += 1
            return row

        if self.exhausted:
            raise StopAsyncIteration

        await self.fetch()

        if self._cache_position < len(self._cache):
            row = self._cache[self._cache_position]
            self._cache_position += 1
            return row

        raise StopAsyncIteration

    def _replace(self, definition: QueryDefinition) -> None:
        self.name = definition["name"]
        self.description = definition["description"]
        self.sql = definition.get("sql")
        self.prompt = definition.get("prompt")
        self.batch_size = definition.get("batch_size")
        self.timeout_ms = definition.get("timeout_ms")
        self.params = definition.get("params")
        self.signature = definition["signature"]
        self.exhausted = False
        self._cache: list[list[Any]] = []
        self._cache_position = 0
        self._fetch_params: list[QueryParameterValue] | None = None
        self._fetch_rows: int | None = None


class QueriesService:
    def __init__(self, peer: rpc.Peer):
        self._peer = peer

    async def create(
        self,
        name: str | None = None,
        *,
        description: str | None = None,
        sql: str | None = None,
        prompt: str | None = None,
        params: list[QueryParameter] | None = None,
        batch_size: int | None = None,
        timeout_ms: int | None = None,
    ) -> Query:
        if prompt is None and (name is None or description is None or sql is None):
            raise ValueError("name, description, and sql are required without a prompt")
        definition_params = _query_params(
            name=name,
            description=description,
            sql=sql,
            prompt=prompt,
            params=params,
            batch_size=batch_size,
            timeout_ms=timeout_ms,
        )
        definition: QueryDefinition = await self._peer.call("queries.create", definition_params)
        return Query(self._peer, definition)

    async def convert(
        self,
        name: str,
        *,
        trigger_name: str | None = None,
        prompt: str | None = None,
        params: list[QueryParameterValue] | None = None,
        schedule: str | None = None,
        batch_size: int | None = None,
        timeout_ms: int | None = None,
        report_noops: bool | None = None,
        enabled: bool | None = None,
    ) -> QueryFetch:
        return await self._peer.call(
            "queries.convert",
            _query_params(
                name=name,
                trigger_name=trigger_name,
                prompt=prompt,
                params=params,
                schedule=schedule,
                batch_size=batch_size,
                timeout_ms=timeout_ms,
                report_noops=report_noops,
                enabled=enabled,
            ),
        )

    async def get(self, name: str | list[str]) -> Query | list[Query]:
        response = await self._peer.call(
            "queries.get",
            {"name": name},
        )
        if isinstance(name, list):
            return [Query(self._peer, definition) for definition in response["queries"]]
        return Query(self._peer, response)

    async def delete(self, name: str | list[str]) -> None:
        await self._peer.call("queries.delete", {"name": name})

    async def list(self) -> list[str]:
        response = await self._peer.call("queries.list")
        return response["queries"]


def _query_params(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}
