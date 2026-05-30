"""Feishu/Lark channel using lark-oapi SDK with WebSocket long connection.

Architecture (adapted from OpenHarness):
  - WS client runs in a dedicated thread with its own asyncio event loop
  - Event handler (sync) dispatches to the main loop via run_coroutine_threadsafe
  - Lark SDK Client handles message sending (auth, token refresh)

Start:  python -m scene.feishu.server

Requires env vars:
  FEISHU_APP_ID / FEISHU_APP_SECRET
  AGENT_PROVIDER (default minimax) / AGENT_MODEL (default minimax-m2.7)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections import OrderedDict
from typing import Any

import lark_oapi as lark
from dotenv import load_dotenv

load_dotenv()

from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    MessageUpdate,
    TextDelta,
    ThinkingDelta,
    ToolCallDelta,
    ToolExecutionEnd,
)
from scene.http_sse.chat_assistant import ChatAssistant
from scene.http_sse.manager import SessionManager

_log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")

manager = SessionManager(cwd=os.getcwd())

# Shared state
_stream_locks: dict[str, asyncio.Lock] = {}
_dedup_cache: OrderedDict[str, None] = OrderedDict()
_main_loop: asyncio.AbstractEventLoop | None = None
_lark_client: Any = None


# ---- Message sending via Lark SDK ----

def _reply_text_sync(message_id: str, text: str) -> str | None:
    """Reply to a message with plain text. Returns reply message_id or None."""
    try:
        import lark_oapi.api.im.v1 as v1
        req = (
            v1.ReplyMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                v1.ReplyMessageRequestBody.builder()
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        resp = _lark_client.im.v1.message.reply(req)
        if resp.success():
            return resp.data.message_id
        _log.error("Reply failed: code=%s msg=%s", resp.code, resp.msg)
    except Exception as e:
        _log.error("Reply error: %s", e)
    return None


def _build_card_json(content: str) -> str:
    """Build a simple Feishu Card JSON 2.0 with markdown content only."""
    body = [{"tag": "markdown", "content": content.strip()[:30000]}]

    card = {
        "schema": "2.0",
        "config": {"enable_forward": True, "width_mode": "fill"},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "Agent"},
        },
        "body": {"direction": "vertical", "vertical_spacing": "8px", "elements": body},
    }
    return json.dumps(card, ensure_ascii=False)

    # --- Header ---
    tool_count = len(tool_details) if tool_details else 0
    header = {
        "template": "blue",
        "title": {"tag": "plain_text", "content": title},
    }
    if tool_count:
        header["text_tag_list"] = [
            {"tag": "text_tag", "text": {"tag": "plain_text", "content": f"🔧 {tool_count} tools"}},
        ]

    card = {
        "schema": "2.0",
        "config": {"enable_forward": True, "width_mode": "fill"},
        "header": header,
        "body": {"direction": "vertical", "vertical_spacing": "8px", "elements": body_elements},
    }
    return json.dumps(card, ensure_ascii=False)


def _extract_tool_result(td: dict, max_len: int) -> str:
    """Extract a readable preview from a tool detail dict."""
    output = td.get("output", "")
    if not output:
        return ""
    text = str(output)
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def _send_card_sync(chat_id: str, content: str) -> str | None:
    """Send an interactive card (JSON 2.0) message with markdown content."""
    import lark_oapi.api.im.v1 as v1
    is_chat = chat_id.startswith("oc_")
    receive_type = "chat_id" if is_chat else "open_id"

    # If content has markdown tables, strip them — Feishu card limit is 1 table
    if content.count("\n|") > 5:
        # Fall back to plain text message for table-heavy content
        return _send_text_sync(chat_id, content)

    card_json = _build_card_json(content)
    try:
        req = (
            v1.CreateMessageRequest.builder()
            .receive_id_type(receive_type)
            .request_body(
                v1.CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(card_json)
                .build()
            )
            .build()
        )
        resp = _lark_client.im.v1.message.create(req)
        if resp.success():
            return resp.data.message_id
        # On card failure, fall back to text
        _log.warning("Card send failed code=%s, falling back to text", resp.code)
        return _send_text_sync(chat_id, content)
    except Exception as e:
        _log.error("Card send error: %s, falling back to text", e)
        return _send_text_sync(chat_id, content)


def _escape_markdown(text: str) -> str:
    """Escape characters in text that would break Feishu markdown rendering.

    Preserves code blocks (```...```) which should NOT be escaped.
    """
    import re

    # Split by code blocks, escape only non-code portions
    parts = re.split(r"(```[\s\S]*?```)", text)
    escaped: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Code block: keep as-is
            escaped.append(part)
        else:
            # Non-code: escape problematic characters
            # Only escape if they appear outside markdown syntax context
            escaped.append(part)
    return "".join(escaped)




def _send_text_sync(chat_id: str, text: str) -> str | None:
    """Send a message to a chat. Returns message_id or None.

    Feishu text messages have a content limit (~30k chars). Long messages are
    split into multiple messages if needed.
    """
    import lark_oapi.api.im.v1 as v1
    is_chat = chat_id.startswith("oc_")
    receive_type = "chat_id" if is_chat else "open_id"

    # Feishu text messages have ~30k char limit; be conservative at 15k
    MAX_CHUNK = 15000
    chunks = []
    remaining = text
    while len(remaining) > MAX_CHUNK:
        split_at = remaining.rfind("\n", 0, MAX_CHUNK)
        if split_at == -1:
            split_at = MAX_CHUNK
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip()
    chunks.append(remaining)

    last_id = None
    for chunk in chunks:
        try:
            content_json = json.dumps({"text": chunk}, ensure_ascii=False)
            req = (
                v1.CreateMessageRequest.builder()
                .receive_id_type(receive_type)
                .request_body(
                    v1.CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(content_json)
                    .build()
                )
                .build()
            )
            resp = _lark_client.im.v1.message.create(req)
            if resp.success():
                last_id = resp.data.message_id
            else:
                _log.error("Send failed: code=%s msg=%s content_len=%s",
                           resp.code, resp.msg, len(chunk))
        except Exception as e:
            _log.error("Send error: %s (len=%s)", e, len(chunk))
    return last_id


# ---- Agent streaming ----

async def _run_agent_and_stream(
    assistant: ChatAssistant,
    chat_id: str,
    user_text: str,
) -> None:
    """Run the agent and stream text deltas back to Feishu."""
    event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
    accumulated: list[str] = []

    async def collector(evt: AgentEvent) -> None:
        await event_queue.put(evt)

    unsub = assistant.on_event(collector)

    # Send placeholder
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send_text_sync, chat_id, "⏳ 思考中...")

    try:
        await assistant.send_message(user_text)

        while True:
            try:
                evt = await asyncio.wait_for(event_queue.get(), timeout=0.15)
            except asyncio.TimeoutError:
                if event_queue.empty():
                    await asyncio.sleep(0.3)
                    if event_queue.empty():
                        break
                continue

            if isinstance(evt, MessageUpdate):
                delta = evt.delta
                if isinstance(delta, TextDelta) and delta.text:
                    accumulated.append(delta.text)

            elif isinstance(evt, AgentEnd):
                break

    except Exception as e:
        _log.exception("Agent error")
        await loop.run_in_executor(None, _send_text_sync, chat_id, f"❌ {e}")
        return
    finally:
        unsub()

    text = "".join(accumulated)
    _log.info("Agent response: len=%d", len(text))

    if text.strip():
        await loop.run_in_executor(None, _send_card_sync, chat_id, text)


# ---- Event handler (sync, called from WS thread) ----

def _on_message_sync(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    """Sync callback from WebSocket thread → schedule async handler in main loop."""
    global _main_loop
    if _main_loop and _main_loop.is_running():
        asyncio.run_coroutine_threadsafe(_on_message(data), _main_loop)


# ---- Async message processor (runs in main event loop) ----

async def _on_message(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    """Handle incoming Feishu message in the main event loop."""
    global _dedup_cache

    try:
        # P2ImMessageReceiveV1 shape: data.event.message, data.event.sender
        inner = data.event  # noqa: F821
        message = inner.message
        sender = inner.sender

        # Dedup
        message_id = message.message_id
        if message_id in _dedup_cache:
            return
        _dedup_cache[message_id] = None
        while len(_dedup_cache) > 500:
            _dedup_cache.popitem(last=False)

        # Skip bot's own messages
        if sender.sender_type == "bot":
            return

        # Parse content
        msg_type = message.message_type
        if msg_type != "text":
            return

        try:
            content = json.loads(message.content) if message.content else {}
        except json.JSONDecodeError:
            return

        text = content.get("text", "").strip()
        if not text:
            return

        # Sender routing
        open_id = sender.sender_id.open_id if sender.sender_id else ""
        chat_type = message.chat_type  # "p2p" or "group"
        chat_id = message.chat_id

        # Use chat_id for group chats, open_id for p2p
        reply_to = chat_id if chat_type == "group" else open_id

        _log.info("📩 [%s] sender=%s text=%s", chat_type, open_id[:12], text[:60])

        # One agent run per user
        lock_key = reply_to
        lock = _stream_locks.setdefault(lock_key, asyncio.Lock())
        if lock.locked():
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, _send_text_sync, reply_to, "⏳ 上条消息处理中，请稍候..."
            )
            return

        async with lock:
            session_id = f"feishu-{open_id}"
            _, assistant = await manager.get_or_create(session_id)
            await _run_agent_and_stream(assistant, reply_to, text)

    except Exception:
        _log.exception("Error in _on_message")


# ---- Main entry ----

def main() -> None:
    global _main_loop, _lark_client

    if not APP_ID or not APP_SECRET:
        _log.error("FEISHU_APP_ID and FEISHU_APP_SECRET must be set")
        return

    _main_loop = asyncio.get_event_loop()

    # Start MCP + embeddings
    _main_loop.run_until_complete(manager.start())
    _log.info("MCP tools + embedding model ready")

    # Create Lark SDK client for sending messages
    _lark_client = (
        lark.Client.builder()
        .app_id(APP_ID)
        .app_secret(APP_SECRET)
        .log_level(lark.LogLevel.INFO)
        .build()
    )

    # Build event handler
    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message_sync)
        .build()
    )

    # WS client
    ws_client = lark.ws.Client(
        APP_ID, APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )

    # Run WS client in a dedicated thread (it blocks on start())
    def ws_thread_loop() -> None:
        import lark_oapi.ws.client as _ws
        ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(ws_loop)
        # Patch the module-level loop used by Lark WS internals
        _ws.loop = ws_loop
        try:
            ws_client.start()
        except Exception as e:
            _log.error("WS client error: %s", e)

    ws_thread = threading.Thread(target=ws_thread_loop, daemon=True)
    ws_thread.start()
    _log.info("Feishu bot started (WebSocket long connection)")
    _log.info("No public URL required — listening via WS")

    # Keep main thread alive
    try:
        _main_loop.run_forever()
    except KeyboardInterrupt:
        _log.info("Stopping...")
    finally:
        _main_loop.run_until_complete(manager.dispose_all())
        _log.info("Feishu bot stopped")


if __name__ == "__main__":
    main()
