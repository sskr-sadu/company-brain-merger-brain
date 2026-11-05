from __future__ import annotations

from typing import Any, TypedDict

import tw2_jsonrpc as rpc


class CursorColumn(TypedDict):
    name: str
    type: str


class CursorOpen(TypedDict):
    sql: str
    signature: list[CursorColumn]
    rows: list[list[Any]]
    cursor: str
    exhausted: bool


class CursorFetch(TypedDict):
    rows: list[list[Any]]
    exhausted: bool


class Cursor:
    def __init__(
        self,
        peer: rpc.Peer,
        *,
        cursor: str,
        sql: str,
        signature: list[CursorColumn],
        rows: list[list[Any]],
        exhausted: bool,
    ):
        self._peer = peer
        self._cursor = cursor
        self.sql = sql
        self.signature = signature
        self.exhausted = exhausted
        self._cache = rows
        self._cache_position = 0

    async def fetch(self) -> list[list[Any]]:
        if self.exhausted:
            return []

        response: CursorFetch = await self._peer.call(
            "cursors.fetch",
            {"cursor": self._cursor},
        )
        self.exhausted = response["exhausted"]
        self._cache.extend(response["rows"])
        return response["rows"]

    async def close(self) -> None:
        await self._peer.call("cursors.close", {"cursor": self._cursor})
        self.exhausted = True

    def __aiter__(self) -> Cursor:
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


class CursorsService:
    def __init__(self, peer: rpc.Peer):
        self._peer = peer

    async def open(
        self,
        *,
        sql: str | None = None,
        prompt: str | None = None,
        batch_size: int | None = None,
        timeout_ms: int | None = None,
    ) -> Cursor:
        if (sql is None) == (prompt is None):
            raise ValueError("exactly one of sql or prompt is required")
        params = _run_params(
            sql=sql,
            prompt=prompt,
            batch_size=batch_size,
            timeout_ms=timeout_ms,
        )
        response: CursorOpen = await self._peer.call("cursors.open", params)
        return Cursor(
            self._peer,
            cursor=response["cursor"],
            sql=response["sql"],
            signature=response["signature"],
            rows=response["rows"],
            exhausted=response["exhausted"],
        )


def _run_params(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}
