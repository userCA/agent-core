from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any

from agent_core.memory.base import MemoryRecord

logger = logging.getLogger(__name__)


class OpenVikingMemoryStore:
    def __init__(
        self,
        client: Any = None,
        *,
        url: str = "http://localhost:1933",
        api_key: str = "",
        api_keys: dict[str, str] | None = None,
        resolve_api_key: Callable[[str], str] | None = None,
        agent_id: str = "",
    ) -> None:
        self._client = client
        self._url = url
        self._api_key = api_key
        self._api_keys = api_keys or {}
        self._resolve_api_key_fn = resolve_api_key
        self._agent_id = agent_id
        self._clients: dict[str, Any] = {}

    def _resolve_api_key(self, session_id: str) -> str:
        if self._resolve_api_key_fn is not None:
            return self._resolve_api_key_fn(session_id)
        if session_id in self._api_keys:
            return self._api_keys[session_id]
        user_id = PurePosixPath(session_id).parts[0]
        if user_id in self._api_keys:
            return self._api_keys[user_id]
        return self._api_key

    def _get_client(self, session_id: str) -> Any:
        if self._client is not None:
            return self._client
        api_key = self._resolve_api_key(session_id)
        if api_key in self._clients:
            return self._clients[api_key]
        import openviking as ov

        kwargs: dict[str, Any] = {"url": self._url}
        if api_key:
            kwargs["api_key"] = api_key
        if self._agent_id:
            kwargs["agent_id"] = self._agent_id
        client = ov.SyncHTTPClient(**kwargs)
        client.initialize()
        self._clients[api_key] = client
        return client

    async def remember(self, *, session_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        try:
            client = self._get_client(session_id)
            payload = text
            if metadata:
                payload = f"{text}\n[metadata: {metadata}]"
            await asyncio.to_thread(
                client.add_message,
                session_id=session_id,
                role="user",
                content=payload,
            )
            await asyncio.to_thread(client.commit_session, session_id=session_id)
        except Exception:
            logger.warning("openviking remember failed for session %s", session_id, exc_info=True)

    async def recall(self, *, session_id: str, query: str, limit: int = 10) -> list[MemoryRecord]:
        try:
            client = self._get_client(session_id)
            result = await asyncio.to_thread(
                client.find,
                query,
                target_uri="viking://user/memories",
                node_limit=limit,
            )
            records: list[MemoryRecord] = []
            for ctx in result.memories:
                records.append(
                    MemoryRecord(
                        text=ctx.abstract or "",
                        session_id=session_id,
                        metadata={
                            "uri": ctx.uri,
                            "score": ctx.score,
                            "context_type": str(ctx.context_type) if ctx.context_type else "",
                            "level": ctx.level,
                        },
                    )
                )
            return records
        except Exception:
            logger.warning("openviking recall failed for session %s", session_id, exc_info=True)
            return []

    async def forget(self, *, session_id: str) -> None:
        try:
            client = self._get_client(session_id)
            await asyncio.to_thread(client.delete_session, session_id=session_id)
        except Exception:
            logger.warning("openviking forget failed for session %s", session_id, exc_info=True)
