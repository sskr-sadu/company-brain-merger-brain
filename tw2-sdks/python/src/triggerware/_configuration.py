from __future__ import annotations

from typing import NotRequired, TypedDict

import tw2_jsonrpc as rpc


class Configuration(TypedDict):
    default_timeout_ms: int
    default_batch_size: int
    default_trigger_batch_size: int
    agent_provider: str
    agent_model: str
    max_log_file_size: str


class Authorization(TypedDict):
    url: NotRequired[str]


class ConfigurationService:
    def __init__(self, peer: rpc.Peer):
        self._peer = peer

    async def get(self) -> Configuration:
        return await self._peer.call("configuration.get")

    async def set(
        self,
        *,
        default_timeout_ms: int | None = None,
        default_batch_size: int | None = None,
        default_trigger_batch_size: int | None = None,
        agent_provider: str | None = None,
        agent_model: str | None = None,
        agent_api_key: str | None = None,
        max_log_file_size: str | None = None,
        secure: bool = False,
    ) -> Configuration | Authorization:
        params = {
            "default_timeout_ms": default_timeout_ms,
            "default_batch_size": default_batch_size,
            "default_trigger_batch_size": default_trigger_batch_size,
            "agent_provider": agent_provider,
            "agent_model": agent_model,
            "agent_api_key": agent_api_key,
            "max_log_file_size": max_log_file_size,
            "secure": secure,
        }
        return await self._peer.call(
            "configuration.set",
            {key: value for key, value in params.items() if value is not None},
        )

    async def refresh(self) -> Configuration:
        return await self._peer.call("configuration.refresh")
