from __future__ import annotations

from inspect import isawaitable
from typing import Any, Awaitable, Callable, NotRequired, TypedDict

import tw2_jsonrpc as rpc


class TriggerSignature(TypedDict):
    name: str
    type: str


class Trigger(TypedDict):
    name: str
    description: str
    prompt: NotRequired[str]
    sql: str
    schedule: NotRequired[str]
    batch_size: NotRequired[int]
    timeout_ms: NotRequired[int]
    report_noops: bool
    enabled: bool
    signature: list[TriggerSignature]


class TriggerDelta(TypedDict):
    added: list[list[Any]]
    deleted: list[list[Any]]


TriggerCallback = Callable[
    [list[list[Any]], list[list[Any]]],
    None | Awaitable[None],
]


class TriggersService:
    def __init__(self, peer: rpc.Peer):
        self._peer = peer

    async def create(
        self,
        name: str | None = None,
        *,
        description: str | None = None,
        sql: str | None = None,
        prompt: str | None = None,
        schedule: str | None = None,
        batch_size: int | None = None,
        timeout_ms: int | None = None,
        report_noops: bool | None = None,
        enabled: bool | None = None,
    ) -> Trigger:
        if prompt is None and (
            name is None or description is None or sql is None or schedule is None
        ):
            raise ValueError("name, description, sql, and schedule are required without a prompt")
        return await self._peer.call(
            "triggers.create",
            _trigger_params(
                name=name,
                description=description,
                sql=sql,
                prompt=prompt,
                schedule=schedule,
                batch_size=batch_size,
                timeout_ms=timeout_ms,
                report_noops=report_noops,
                enabled=enabled,
            ),
        )

    async def get(self, name: str | list[str]) -> Trigger | list[Trigger]:
        response = await self._peer.call("triggers.get", {"name": name})
        return response["triggers"] if isinstance(name, list) else response

    async def update(
        self,
        name: str,
        *,
        description: str | None = None,
        sql: str | None = None,
        prompt: str | None = None,
        schedule: str | None = None,
        batch_size: int | None = None,
        timeout_ms: int | None = None,
        report_noops: bool | None = None,
        enabled: bool | None = None,
    ) -> Trigger:
        return await self._peer.call(
            "triggers.update",
            _trigger_params(
                name=name,
                description=description,
                sql=sql,
                prompt=prompt,
                schedule=schedule,
                batch_size=batch_size,
                timeout_ms=timeout_ms,
                report_noops=report_noops,
                enabled=enabled,
            ),
        )

    async def list(self) -> list[str]:
        response = await self._peer.call("triggers.list")
        return response["triggers"]

    async def delete(self, name: str | list[str]) -> None:
        await self._peer.call("triggers.delete", {"name": name})

    async def enable(self, name: str) -> None:
        await self._peer.call("triggers.enable", {"name": name})

    async def disable(self, name: str) -> None:
        await self._peer.call("triggers.disable", {"name": name})

    async def run(
        self,
        name: str,
        *,
        batch_size: int | None = None,
        timeout_ms: int | None = None,
    ) -> TriggerDelta:
        return await self._peer.call(
            "triggers.run",
            _trigger_params(name=name, batch_size=batch_size, timeout_ms=timeout_ms),
        )

    async def poll(self, name: str) -> list[TriggerDelta]:
        response = await self._peer.call("triggers.poll", {"name": name})
        return response["deltas"]

    async def watch(
        self,
        name: str,
        callback: TriggerCallback,
        *,
        resume_window_ms: int | None = None,
    ) -> str:
        self._register_watcher(name, callback)
        response = await self._peer.call(
            "triggers.watch",
            _trigger_params(name=name, resume_window_ms=resume_window_ms),
        )
        return response["resume_token"]

    async def resume(
        self,
        name: str,
        resume_token: str,
        callback: TriggerCallback,
        *,
        resume_window_ms: int | None = None,
    ) -> str:
        self._register_watcher(name, callback)
        response = await self._peer.call(
            "triggers.resume",
            _trigger_params(
                name=name,
                resume_token=resume_token,
                resume_window_ms=resume_window_ms,
            ),
        )
        return response["resume_token"]

    async def unwatch(
        self,
        *,
        name: str | None = None,
        resume_token: str | None = None,
    ) -> None:
        if name is None and resume_token is None:
            raise ValueError("name or resume_token is required")
        await self._peer.call(
            "triggers.unwatch",
            _trigger_params(name=name, resume_token=resume_token),
        )

    def _register_watcher(self, name: str, callback: TriggerCallback) -> None:
        async def handler(params: dict[str, Any]) -> None:
            for delta in params["deltas"]:
                result = callback(delta["added"], delta["deleted"])
                if isawaitable(result):
                    await result

        self._peer.add_method(name, handler)


def _trigger_params(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}
