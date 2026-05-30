"""Feishu/Lark multi-tenant bot runner.

Supports multiple bot instances in one process — each enabled feishu
channel in .pi/channels.json gets its own WS connection + Lark client.

Start:  python -m scene.feishu.server
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import lark_oapi as lark
from dotenv import load_dotenv

load_dotenv()

from agent_core.core.events import AgentEnd, AgentEvent, MessageUpdate, TextDelta
from scene.http_sse.channel_config import load_channels
from scene.http_sse.manager import SessionManager

_log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DEDUP_TTL = 24 * 3600
DEDUP_PATH = Path(os.getcwd()) / ".pi" / "feishu_seen_ids.json"
BATCH_DELAY = 0.6
BATCH_MAX_CHARS = 4000

manager = SessionManager(cwd=os.getcwd())
_stream_locks: dict[str, asyncio.Lock] = {}
_dedup_ids: OrderedDict[str, float] = OrderedDict()
_main_loop: asyncio.AbstractEventLoop | None = None

# Per-channel state: channel_id → {client, ws_client, ws_thread, data}
_channels: dict[str, dict[str, Any]] = {}

# ---- Regex for format detection ----

_MD_TABLE_RE = re.compile(r"^\|.+\|.*\n\|[-:\s|]+\|", re.MULTILINE)
_MD_HINT_RE = re.compile(
    r"(^#{1,6}\s)|(^\s*[-*]\s)|(^\s*\d+\.\s)|(```)|(\*\*[^*\n].+?\*\*)|"
    r"(~~[^~\n].+?~~)|(\[[^\]]+\]\([^)]+\))|(^>\s)",
    re.MULTILINE,
)
_FENCE_OPEN_RE = re.compile(r"^```([^\n`]*)\s*$")
_FENCE_CLOSE_RE = re.compile(r"^```\s*$")

# ---- Dedup ----

def _load_dedup() -> None:
    try:
        data = json.loads(DEDUP_PATH.read_text(encoding="utf-8"))
        valid = {k: v for k, v in data.get("ids", {}).items() if time.time() - v < DEDUP_TTL}
        _dedup_ids.update(sorted(valid.items(), key=lambda x: x[1], reverse=True)[:2048])
    except Exception:
        pass


def _save_dedup() -> None:
    try:
        DEDUP_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEDUP_PATH.write_text(json.dumps({"ids": dict(_dedup_ids)}, ensure_ascii=False))
    except Exception:
        pass


def _is_duplicate(msg_id: str) -> bool:
    now = time.time()
    if msg_id in _dedup_ids and now - _dedup_ids[msg_id] < DEDUP_TTL:
        return True
    _dedup_ids[msg_id] = now
    _dedup_ids.move_to_end(msg_id)
    while len(_dedup_ids) > 2048:
        _dedup_ids.popitem(last=False)
    _save_dedup()
    return False


# ---- Smart format ----

def _choose_format(content: str) -> str:
    if _MD_TABLE_RE.search(content): return "text"
    if _MD_HINT_RE.search(content) or len(content) > 2000: return "interactive"
    if len(content) > 200: return "post"
    return "text"


def _build_post_payload(content: str) -> str:
    rows: list[list[dict]] = []
    cur: list[str] = []
    in_fence = False
    for line in content.split("\n"):
        s = line.strip()
        if _FENCE_OPEN_RE.match(s) and not in_fence:
            if cur: rows.append([{"tag": "text", "text": "\n".join(cur)}]); cur = []
            in_fence = True
        elif _FENCE_CLOSE_RE.match(s) and in_fence:
            cur.append(line); rows.append([{"tag": "text", "text": "\n".join(cur)}]); cur = []; in_fence = False
        else:
            cur.append(line)
    if cur: rows.append([{"tag": "text", "text": "\n".join(cur)}])
    return json.dumps({"zh_cn": {"content": rows or [[{"tag": "text", "text": content}]]}}, ensure_ascii=False)


# ---- Per-channel message sending ----

def _send(channel_id: str, chat_id: str, content: str) -> str | None:
    """Send message using the channel's Lark client."""
    import lark_oapi.api.im.v1 as v1
    ch = _channels.get(channel_id)
    if not ch:
        return None
    client = ch["client"]
    is_chat = chat_id.startswith("oc_")
    receive_type = "chat_id" if is_chat else "open_id"
    fmt = _choose_format(content)

    if fmt == "text":
        payload = json.dumps({"text": content}, ensure_ascii=False)
    elif fmt == "post":
        payload = _build_post_payload(content)
    else:
        payload = json.dumps({
            "schema": "2.0", "config": {"enable_forward": True, "width_mode": "fill"},
            "header": {"template": "blue", "title": {"tag": "plain_text", "content": ch["name"]}},
            "body": {"direction": "vertical", "vertical_spacing": "8px",
                     "elements": [{"tag": "markdown", "content": content[:30000]}]},
        }, ensure_ascii=False)

    try:
        req = (v1.CreateMessageRequest.builder().receive_id_type(receive_type)
               .request_body(v1.CreateMessageRequestBody.builder()
                             .receive_id(chat_id).msg_type(fmt).content(payload).build()).build())
        resp = client.im.v1.message.create(req)
        if resp.success(): return resp.data.message_id
        if fmt != "text":
            fb = json.dumps({"text": content}, ensure_ascii=False)
            req2 = (v1.CreateMessageRequest.builder().receive_id_type(receive_type)
                    .request_body(v1.CreateMessageRequestBody.builder()
                                  .receive_id(chat_id).msg_type("text").content(fb).build()).build())
            resp2 = client.im.v1.message.create(req2)
            if resp2.success(): return resp2.data.message_id
        _log.error("[%s] Send failed: code=%s msg=%s", channel_id, resp.code, resp.msg)
    except Exception as e:
        _log.error("[%s] Send error: %s", channel_id, e)
    return None


# ---- Batching (per-channel key) ----

_batch_buf: dict[str, dict[str, Any]] = {}
_batch_tasks: dict[str, asyncio.Task] = {}


async def _flush_batch(key: str) -> None:
    await asyncio.sleep(BATCH_DELAY)
    entry = _batch_buf.pop(key, None)
    _batch_tasks.pop(key, None)
    if not entry:
        return
    await _process_one(entry["channel_id"], entry["open_id"], entry["reply_to"], entry["text"])


def _enqueue_batch(channel_id: str, open_id: str, reply_to: str, text: str, chat_type: str) -> None:
    key = f"{channel_id}:{open_id}:{chat_type}"
    existing = _batch_buf.get(key)
    if existing and existing.get("reply_to") == reply_to:
        existing["text"] = f"{existing['text']}\n{text}"[:BATCH_MAX_CHARS]
        task = _batch_tasks.get(key)
        if task and not task.done(): task.cancel()
    else:
        _batch_buf[key] = {"channel_id": channel_id, "open_id": open_id, "reply_to": reply_to, "text": text}
    _batch_tasks[key] = asyncio.create_task(_flush_batch(key))


# ---- Agent processing ----

async def _process_one(channel_id: str, open_id: str, reply_to: str, user_text: str) -> None:
    lock = _stream_locks.setdefault(reply_to, asyncio.Lock())
    if lock.locked():
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send, channel_id, reply_to, "⏳ 上条消息处理中，请稍候...")
        return

    async with lock:
        # Session per channel + user — different channels get different agents
        session_id = f"feishu-{channel_id}-{open_id}"
        _, assistant = await manager.get_or_create(session_id)

        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        accumulated: list[str] = []

        async def collector(evt: AgentEvent) -> None:
            await queue.put(evt)

        unsub = assistant.on_event(collector)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send, channel_id, reply_to, "⏳ 思考中...")

        try:
            await assistant.send_message(user_text)
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=0.15)
                except asyncio.TimeoutError:
                    if queue.empty():
                        await asyncio.sleep(0.3)
                        if queue.empty(): break
                    continue
                if isinstance(evt, MessageUpdate):
                    delta = evt.delta
                    if isinstance(delta, TextDelta) and delta.text:
                        accumulated.append(delta.text)
                elif isinstance(evt, AgentEnd):
                    break
        except Exception:
            _log.exception("[%s] Agent error", channel_id)
            await loop.run_in_executor(None, _send, channel_id, reply_to, "❌ Agent 处理出错")
        finally:
            unsub()

        text = "".join(accumulated)
        _log.info("[%s] Agent response: len=%d", channel_id, len(text))
        if text.strip():
            await loop.run_in_executor(None, _send, channel_id, reply_to, text)


# ---- Event handler factory (each channel gets its own) ----

def _make_on_message_sync(channel_id: str):
    """Create a sync handler that remembers which channel it belongs to."""
    def handler(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        if _main_loop and _main_loop.is_running():
            asyncio.run_coroutine_threadsafe(_on_message(channel_id, data), _main_loop)
    return handler


async def _on_message(channel_id: str, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    try:
        inner = data.event
        message = inner.message
        sender = inner.sender

        msg_id = message.message_id
        if not msg_id or _is_duplicate(msg_id): return
        if sender.sender_type == "bot": return
        if message.message_type != "text": return
        try:
            content = json.loads(message.content) if message.content else {}
        except json.JSONDecodeError:
            return
        text = content.get("text", "").strip()
        if not text: return

        open_id = sender.sender_id.open_id if sender.sender_id else ""
        chat_type = message.chat_type
        reply_to = message.chat_id if chat_type == "group" else open_id

        _log.info("[%s] 📩 [%s] %s: %s", channel_id, chat_type, open_id[:12], text[:60])
        _enqueue_batch(channel_id, open_id, reply_to, text, chat_type)
    except Exception:
        _log.exception("[%s] _on_message", channel_id)


# ---- Bot instance lifecycle ----

def _start_bot(ch: dict) -> None:
    """Start a single bot instance for one channel."""
    channel_id = ch["id"]
    if channel_id in _channels:
        _log.warning("[%s] Already running", channel_id)
        return

    client = (lark.Client.builder()
              .app_id(ch["app_id"]).app_secret(ch["app_secret"])
              .log_level(lark.LogLevel.WARNING).build())

    handler = (lark.EventDispatcherHandler.builder("", "")
               .register_p2_im_message_receive_v1(_make_on_message_sync(channel_id))
               .build())

    ws_client = lark.ws.Client(
        ch["app_id"], ch["app_secret"],
        event_handler=handler, log_level=lark.LogLevel.INFO,
    )

    def _ws_run() -> None:
        import lark_oapi.ws.client as _ws
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _ws.loop = loop
        try:
            ws_client.start()
        except Exception as e:
            if getattr(ws_client, "_auto_reconnect", True):
                _log.error("[%s] WS error: %s", channel_id, e)

    thread = threading.Thread(target=_ws_run, daemon=True, name=f"feishu-{channel_id}")
    thread.start()

    _channels[channel_id] = {
        "id": channel_id, "name": ch.get("name", channel_id),
        "config": ch, "client": client, "ws_client": ws_client, "thread": thread,
    }
    _log.info("[%s] Bot started: %s", channel_id, ch["name"])


def _stop_bot(channel_id: str) -> None:
    """Stop a bot instance."""
    state = _channels.pop(channel_id, None)
    if not state:
        return
    try:
        setattr(state["ws_client"], "_auto_reconnect", False)
    except Exception:
        pass
    _log.info("[%s] Bot stopped", channel_id)


def _sync_channels() -> None:
    """Synchronize running bots with channel config."""
    channels = load_channels(os.getcwd())
    feishu_channels = [c for c in channels if c["type"] == "feishu" and c.get("enabled")]

    # Start new / changed channels
    running_ids = set(_channels.keys())
    config_ids = {c["id"] for c in feishu_channels}
    for ch in feishu_channels:
        if ch["id"] not in running_ids:
            _start_bot(ch)
        else:
            existing = _channels[ch["id"]]
            if (existing["config"].get("app_id") != ch.get("app_id") or
                existing["config"].get("app_secret") != ch.get("app_secret")):
                _stop_bot(ch["id"])
                _start_bot(ch)

    # Stop removed / disabled channels
    for rid in running_ids - config_ids:
        _stop_bot(rid)


# ---- Main ----

def main() -> None:
    global _main_loop
    _main_loop = asyncio.get_event_loop()
    _main_loop.run_until_complete(manager.start())
    _load_dedup()
    _log.info("Ready (dedup: %d ids)", len(_dedup_ids))

    # Start all enabled feishu channels
    _sync_channels()
    if not _channels:
        _log.warning("No enabled feishu channels found in .pi/channels.json or env")
        _log.info("Configure channels at http://localhost:8001 → 渠道管理")

    _log.info("Running %d bot(s): %s", len(_channels), list(_channels.keys()))

    # Periodic config watcher for hot reload (every 30s)
    async def _watch_config() -> None:
        while True:
            await asyncio.sleep(30)
            try:
                _sync_channels()
            except Exception:
                _log.debug("Config watch error", exc_info=True)

    _main_loop.create_task(_watch_config())

    try:
        _main_loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for rid in list(_channels.keys()):
            _stop_bot(rid)
        _main_loop.run_until_complete(manager.dispose_all())
        _log.info("Stopped")


if __name__ == "__main__":
    main()
