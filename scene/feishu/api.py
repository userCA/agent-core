"""Feishu Open API client — token management and message sending."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

_log = logging.getLogger(__name__)

FEISHU_BASE = "https://open.feishu.cn/open-apis"

# Cache token with expiry (tenant token TTL is ~2h)
_token_cache: dict[str, Any] = {"token": "", "expires_at": 0}


async def _get_tenant_token(app_id: str, app_secret: str) -> str:
    """Get or refresh a tenant access token."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu token error: {data}")

        _token_cache["token"] = data["tenant_access_token"]
        _token_cache["expires_at"] = now + data.get("expire", 7200)
        return _token_cache["token"]


async def reply_message(
    message_id: str,
    content: str,
    *,
    app_id: str,
    app_secret: str,
    msg_type: str = "text",
) -> dict[str, Any]:
    """Reply to a Feishu message in-thread."""
    token = await _get_tenant_token(app_id, app_secret)

    if msg_type == "text":
        body = {"content": json.dumps({"text": content})}
    elif msg_type == "interactive":
        body = {"content": content}
    else:
        body = {"content": content}

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{FEISHU_BASE}/im/v1/messages/{message_id}/reply",
            json={"msg_type": msg_type, **body},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code != 200:
            _log.error("Feishu reply %s → %s %s", message_id[:20], resp.status_code, resp.text[:300])
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu reply error: {data}")
        return data


async def send_message(
    receive_id: str,
    content: str,
    *,
    app_id: str,
    app_secret: str,
    msg_type: str = "text",
    receive_id_type: str = "open_id",
) -> dict[str, Any]:
    """Send a direct message to a Feishu user."""
    token = await _get_tenant_token(app_id, app_secret)

    if msg_type == "text":
        body = {"content": json.dumps({"text": content})}

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{FEISHU_BASE}/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            json={
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": json.dumps({"text": content}),
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu send error: {data}")
        return data


async def patch_message(
    message_id: str,
    content: str,
    *,
    app_id: str,
    app_secret: str,
) -> dict[str, Any]:
    """Update (edit) an existing bot message.

    Note: Feishu only allows editing messages sent by the bot itself,
    and only within a short time window. Used for simulated streaming.
    """
    token = await _get_tenant_token(app_id, app_secret)

    # Truncate to Feishu text message limit (~30k chars for content JSON)
    safe = content[:10000] if len(content) > 10000 else content

    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{FEISHU_BASE}/im/v1/messages/{message_id}",
            json={"msg_type": "text", "content": json.dumps({"text": safe})},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code != 200:
            _log.error("Feishu patch %s → %s %s", message_id[:20], resp.status_code, resp.text[:200])
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu patch error: {data}")
        return data
