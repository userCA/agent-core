"""Optional Langfuse Score submission via Public API (no langfuse SDK)."""

from __future__ import annotations

import logging
import os

import httpx

_log = logging.getLogger(__name__)


def _langfuse_enabled() -> bool:
    return os.environ.get("LANGFUSE_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _langfuse_credentials() -> tuple[str, str, str] | None:
    if not _langfuse_enabled():
        return None
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    if not pk or not sk:
        return None
    base = os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").rstrip("/")
    return pk, sk, base


async def submit_user_score(
    *,
    run_id: str,
    session_id: str = "",
    value: float,
    comment: str = "",
) -> bool:
    """Post a numeric user-feedback score to Langfuse. Returns False when skipped or failed."""
    creds = _langfuse_credentials()
    if creds is None:
        return False

    pk, sk, base = creds
    url = f"{base}/api/public/scores"
    payload: dict[str, object] = {
        "name": "user-feedback",
        "value": value,
        "dataType": "NUMERIC",
        "comment": comment or "",
        "metadata": {"run_id": run_id},
    }
    if session_id:
        payload["sessionId"] = session_id

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, auth=(pk, sk))
            resp.raise_for_status()
        return True
    except Exception as exc:
        _log.warning("Langfuse score submission failed: %s", exc)
        return False
