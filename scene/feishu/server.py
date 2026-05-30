"""Feishu/Lark bot — WebSocket long connection with agent-core.

Core: message dedup (24h), split-message batching (0.6s),
smart format (text/post/interactive), reliable send/receive.

Start:  python -m scene.feishu.server
Requires: FEISHU_APP_ID, FEISHU_APP_SECRET, (AGENT_PROVIDER, AGENT_MODEL)
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
from scene.http_sse.manager import SessionManager

_log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
DEDUP_TTL = 24 * 3600
DEDUP_PATH = Path(os.getcwd()) / ".pi" / "feishu_seen_ids.json"
BATCH_DELAY = 0.6
BATCH_MAX_CHARS = 4000

manager = SessionManager(cwd=os.getcwd())
_stream_locks: dict[str, asyncio.Lock] = {}
_dedup_ids: OrderedDict[str, float] = OrderedDict()
_main_loop: asyncio.AbstractEventLoop | None = None
_lark_client: Any = None

# ---- Regex for content format detection ----

_MD_TABLE_RE = re.compile(r"^\|.+\|.*\n\|[-:\s|]+\|", re.MULTILINE)
_MD_HINT_RE = re.compile(
    r"(^#{1,6}\s)|(^\s*[-*]\s)|(^\s*\d+\.\s)|(```)|(\*\*[^*\n].+?\*\*)|"
    r"(~~[^~\n].+?~~)|(\[[^\]]+\]\([^)]+\))|(^>\s)",
    re.MULTILINE,
)
_FENCE_OPEN_RE = re.compile(r"^```([^\n`]*)\s*$")
_FENCE_CLOSE_RE = re.compile(r"^```\s*$")

# ---- Persistent dedup ----

def _load_dedup() -> None:
    try:
        data = json.loads(DEDUP_PATH.read_text(encoding="utf-8"))
        ids = data.get("ids", {})
        now = time.time()
        valid = {k: v for k, v in ids.items() if now - v < DEDUP_TTL}
        _dedup_ids.update(
            sorted(valid.items(), key=lambda x: x[1], reverse=True)[:2048]
        )
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


# ---- Smart format detection ----

def _choose_format(content: str) -> str:
    """Best Feishu message format: text, post, or interactive."""
    if _MD_TABLE_RE.search(content):
        return "text"
    if _MD_HINT_RE.search(content) or len(content) > 2000:
        return "interactive"
    if len(content) > 200:
        return "post"
    return "text"


def _build_post_payload(content: str) -> str:
    rows: list[list[dict]] = []
    cur: list[str] = []
    in_fence = False
    for line in content.split("\n"):
        s = line.strip()
        if _FENCE_OPEN_RE.match(s) and not in_fence:
            if cur:
                rows.append([{"tag": "text", "text": "\n".join(cur)}]); cur = []
            in_fence = True
        elif _FENCE_CLOSE_RE.match(s) and in_fence:
            cur.append(line); rows.append([{"tag": "text", "text": "\n".join(cur)}]); cur = []; in_fence = False
        else:
            cur.append(line)
    if cur:
        rows.append([{"tag": "text", "text": "\n".join(cur)}])
    return json.dumps({"zh_cn": {"content": rows or [[{"tag": "text", "text": content}]]}}, ensure_ascii=False)


# ---- Message sending (sync, called via run_in_executor) ----

def _send(chat_id: str, content: str) -> str | None:
    """Send with auto format detection. Returns message_id or None."""
    import lark_oapi.api.im.v1 as v1
    is_chat = chat_id.startswith("oc_")
    receive_type = "chat_id" if is_chat else "open_id"
    fmt = _choose_format(content)

    if fmt == "text":
        payload = json.dumps({"text": content}, ensure_ascii=False)
    elif fmt == "post":
        payload = _build_post_payload(content)
    else:
        payload = json.dumps({
            "schema": "2.0",
            "config": {"enable_forward": True, "width_mode": "fill"},
            "header": {"template": "blue", "title": {"tag": "plain_text", "content": "Agent"}},
            "body": {"direction": "vertical", "vertical_spacing": "8px",
                     "elements": [{"tag": "markdown", "content": content[:30000]}]},
        }, ensure_ascii=False)

    try:
        req = (
            v1.CreateMessageRequest.builder()
            .receive_id_type(receive_type)
            .request_body(v1.CreateMessageRequestBody.builder()
                          .receive_id(chat_id).msg_type(fmt).content(payload).build())
            .build()
        )
        resp = _lark_client.im.v1.message.create(req)
        if resp.success():
            return resp.data.message_id
        # Fallback card/post → text
        if fmt != "text":
            fb = json.dumps({"text": content}, ensure_ascii=False)
            req2 = (
                v1.CreateMessageRequest.builder()
                .receive_id_type(receive_type)
                .request_body(v1.CreateMessageRequestBody.builder()
                              .receive_id(chat_id).msg_type("text").content(fb).build())
                .build()
            )
            resp2 = _lark_client.im.v1.message.create(req2)
            if resp2.success():
                return resp2.data.message_id
        _log.error("Send failed: code=%s msg=%s", resp.code, resp.msg)
    except Exception as e:
        _log.error("Send error: %s", e)
    return None


# ---- Message batching ----

_batch_buf: dict[str, dict[str, Any]] = {}
_batch_tasks: dict[str, asyncio.Task] = {}


async def _flush_batch(key: str) -> None:
    await asyncio.sleep(BATCH_DELAY)
    entry = _batch_buf.pop(key, None)
    _batch_tasks.pop(key, None)
    if not entry:
        return
    await _process_one(entry["open_id"], entry["reply_to"], entry["text"])


def _enqueue_batch(open_id: str, reply_to: str, text: str, chat_type: str) -> None:
    key = f"{open_id}:{chat_type}"
    existing = _batch_buf.get(key)
    if existing and existing.get("reply_to") == reply_to:
        existing["text"] = f"{existing['text']}\n{text}"[:BATCH_MAX_CHARS]
        task = _batch_tasks.get(key)
        if task and not task.done():
            task.cancel()
    else:
        _batch_buf[key] = {"open_id": open_id, "reply_to": reply_to, "text": text}
    _batch_tasks[key] = asyncio.create_task(_flush_batch(key))


# ---- Agent processing (async, runs in main event loop) ----

async def _process_one(open_id: str, reply_to: str, user_text: str) -> None:
    lock = _stream_locks.setdefault(reply_to, asyncio.Lock())
    if lock.locked():
        _log.info("Busy for %s, sending wait hint", reply_to[:12])
        await asyncio.get_running_loop().run_in_executor(
            None, _send, reply_to, "⏳ 上条消息处理中，请稍候..."
        )
        return

    async with lock:
        session_id = f"feishu-{open_id}"
        _, assistant = await manager.get_or_create(session_id)

        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        accumulated: list[str] = []

        async def collector(evt: AgentEvent) -> None:
            await queue.put(evt)

        unsub = assistant.on_event(collector)

        # Placeholder message
        await asyncio.get_running_loop().run_in_executor(
            None, _send, reply_to, "⏳ 思考中..."
        )

        try:
            await assistant.send_message(user_text)
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=0.15)
                except asyncio.TimeoutError:
                    if queue.empty():
                        await asyncio.sleep(0.3)
                        if queue.empty():
                            break
                    continue
                if isinstance(evt, MessageUpdate):
                    delta = evt.delta
                    if isinstance(delta, TextDelta) and delta.text:
                        accumulated.append(delta.text)
                elif isinstance(evt, AgentEnd):
                    break
        except Exception:
            _log.exception("Agent error")
            await asyncio.get_running_loop().run_in_executor(
                None, _send, reply_to, "❌ Agent 处理出错"
            )
        finally:
            unsub()

        text = "".join(accumulated)
        _log.info("Agent response: len=%d", len(text))
        if text.strip():
            await asyncio.get_running_loop().run_in_executor(
                None, _send, reply_to, text
            )


# ---- Event handlers ----

def _on_message_sync(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    if _main_loop and _main_loop.is_running():
        asyncio.run_coroutine_threadsafe(_on_message(data), _main_loop)


async def _on_message(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    try:
        inner = data.event
        message = inner.message
        sender = inner.sender

        msg_id = message.message_id
        if not msg_id or _is_duplicate(msg_id):
            return
        if sender.sender_type == "bot":
            return
        if message.message_type != "text":
            return
        try:
            content = json.loads(message.content) if message.content else {}
        except json.JSONDecodeError:
            return
        text = content.get("text", "").strip()
        if not text:
            return

        open_id = sender.sender_id.open_id if sender.sender_id else ""
        chat_type = message.chat_type
        reply_to = message.chat_id if chat_type == "group" else open_id

        _log.info("📩 [%s] %s: %s", chat_type, open_id[:12], text[:60])
        _enqueue_batch(open_id, reply_to, text, chat_type)
    except Exception:
        _log.exception("_on_message")


# ---- Main ----

def main() -> None:
    global _main_loop, _lark_client

    if not APP_ID or not APP_SECRET:
        _log.error("FEISHU_APP_ID and FEISHU_APP_SECRET must be set")
        return

    _main_loop = asyncio.get_event_loop()
    _main_loop.run_until_complete(manager.start())
    _load_dedup()
    _log.info("Ready (dedup: %d ids)", len(_dedup_ids))

    _lark_client = (
        lark.Client.builder()
        .app_id(APP_ID).app_secret(APP_SECRET)
        .log_level(lark.LogLevel.WARNING).build()
    )

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message_sync)
        .build()
    )
    ws_client = lark.ws.Client(
        APP_ID, APP_SECRET, event_handler=handler, log_level=lark.LogLevel.INFO,
    )

    def _ws_run() -> None:
        import lark_oapi.ws.client as _ws
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _ws.loop = loop
        try:
            ws_client.start()
        except Exception as e:
            _log.error("WS error: %s", e)

    threading.Thread(target=_ws_run, daemon=True).start()
    _log.info("Feishu bot started")

    try:
        _main_loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _main_loop.run_until_complete(manager.dispose_all())
        _log.info("Stopped")


if __name__ == "__main__":
    main()
