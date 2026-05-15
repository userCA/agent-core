# HTTP SSE 聊天助手场景 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `scene/http_sse/` 下的 FastAPI HTTP SSE 服务端，提供流式聊天接口和 HTML demo 页面。

**Architecture:** 三层分离：
1. `events.py` — AgentEvent → SSE JSON 格式转换
2. `manager.py` — SessionManager（SessionStore + ChatAssistant 生命周期）
3. `server.py` — FastAPI 路由 + HTML 页面

**Tech Stack:** FastAPI, uvicorn, asyncio.Queue, JsonlStore

**Spec:** `docs/superpowers/specs/2026-05-14-http-sse-scene.md`

**Note:** 本仓库当前不是 git 仓库，实施步骤里不包含 `git add` / `git commit`。

---

## File Structure

**新建：**
- `scene/http_sse/events.py` — AgentEvent → SSE JSON 转换
- `scene/http_sse/manager.py` — SessionManager
- `scene/http_sse/server.py` — FastAPI app（替换现有占位文件）
- `scene/http_sse/static/index.html` — HTML demo 页面
- `tests/scene/test_http_sse.py` — 单元测试

**修改：**
- `pyproject.toml` — 增加 fastapi, uvicorn 依赖

**不变（已有）：**
- `scene/http_sse/__init__.py`
- `scene/http_sse/chat_assistant.py`
- `scene/http_sse/system_prompt.py`

---

## Task 1: 更新 pyproject.toml 添加依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 在 `dependencies` 列表中追加 fastapi 和 uvicorn**

修改 `/Users/yuanbaishu/pythonProject/agent-core/pyproject.toml` 的 `dependencies` 列表：

```toml
dependencies = [
    "pydantic>=2.5",
    "httpx>=0.27",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.30",
]
```

- [ ] **Step 2: 验证 toml 语法**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core && python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb')); print('toml OK')"
```

Expected: `toml OK`

---

## Task 2: 实现 events.py（AgentEvent → SSE JSON 转换）

**Files:**
- Create: `scene/http_sse/events.py`
- Test: `tests/scene/test_http_sse.py`（先写 events 相关测试）

- [ ] **Step 1: 写测试 — 验证 text_delta 转换**

在 `tests/scene/test_http_sse.py` 写入：

```python
"""Tests for HTTP SSE scene."""

from __future__ import annotations

from agent_core.core.events import (
    MessageEnd,
    MessageUpdate,
    TextDelta,
    ThinkingDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
)
from scene.http_sse.events import agent_event_to_sse_json


def test_text_delta():
    evt = MessageUpdate(message=None, delta=TextDelta(text="Hello"))
    result = agent_event_to_sse_json(evt)
    assert result == {"event": "text_delta", "text": "Hello"}


def test_thinking_delta():
    evt = MessageUpdate(message=None, delta=ThinkingDelta(text="Hmm"))
    result = agent_event_to_sse_json(evt)
    assert result == {"event": "thinking_delta", "text": "Hmm"}


def test_tool_start():
    evt = ToolExecutionStart(tool_call_id="tc1", tool_name="ls", args={"path": "/tmp"})
    result = agent_event_to_sse_json(evt)
    assert result == {"event": "tool_start", "tool_name": "ls", "args": {"path": "/tmp"}}


def test_tool_end():
    evt = ToolExecutionEnd(
        tool_call_id="tc1", tool_name="ls", result="file.txt", is_error=False
    )
    result = agent_event_to_sse_json(evt)
    assert result == {
        "event": "tool_end",
        "tool_name": "ls",
        "result": "file.txt",
        "is_error": False,
    }


def test_message_end_with_usage():
    class FakeUsage:
        input_tokens = 10
        output_tokens = 5
        cache_read_tokens = 0
        cache_write_tokens = 0
        total_tokens = 15

    msg = {"usage": FakeUsage()}
    evt = MessageEnd(message=msg)
    result = agent_event_to_sse_json(evt)
    assert result == {
        "event": "message_end",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        },
    }


def test_message_end_without_usage():
    evt = MessageEnd(message={})
    result = agent_event_to_sse_json(evt)
    assert result == {"event": "message_end", "usage": None}


def test_unsupported_events_return_none():
    from agent_core.core.events import AgentStart, TurnStart

    assert agent_event_to_sse_json(AgentStart()) is None
    assert agent_event_to_sse_json(TurnStart()) is None
```

- [ ] **Step 2: 运行测试，确认失败**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core && python -m pytest tests/scene/test_http_sse.py -v
```

Expected: 全部 FAIL（`agent_event_to_sse_json` 未定义）

- [ ] **Step 3: 实现 `scene/http_sse/events.py`**

创建 `/Users/yuanbaishu/pythonProject/agent-core/scene/http_sse/events.py`，写入：

```python
"""AgentEvent to SSE JSON event format conversion."""

from __future__ import annotations

from typing import Any

from agent_core.core.events import (
    AgentEvent,
    MessageEnd,
    MessageUpdate,
    TextDelta,
    ThinkingDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolCallDelta,
)


def agent_event_to_sse_json(evt: AgentEvent) -> dict[str, Any] | None:
    """Convert an AgentEvent to an SSE JSON dict.

    Returns None for events that should not be sent to the client.
    """
    if isinstance(evt, MessageUpdate):
        delta = evt.delta
        if isinstance(delta, TextDelta):
            return {"event": "text_delta", "text": delta.text}
        elif isinstance(delta, ThinkingDelta):
            return {"event": "thinking_delta", "text": delta.text}
        elif isinstance(delta, ToolCallDelta):
            return None
        return None

    if isinstance(evt, ToolExecutionStart):
        return {
            "event": "tool_start",
            "tool_name": evt.tool_name,
            "args": evt.args,
        }

    if isinstance(evt, ToolExecutionEnd):
        return {
            "event": "tool_end",
            "tool_name": evt.tool_name,
            "result": _extract_result_text(evt.result),
            "is_error": evt.is_error,
        }

    if isinstance(evt, MessageEnd):
        usage = None
        msg = evt.message
        if hasattr(msg, "usage") and msg.usage:
            u = msg.usage
            usage = {
                "input_tokens": getattr(u, "input_tokens", 0),
                "output_tokens": getattr(u, "output_tokens", 0),
                "total_tokens": getattr(u, "total_tokens", 0),
            }
        return {"event": "message_end", "usage": usage}

    return None


def _extract_result_text(result: Any) -> str:
    """Extract text from a ToolResult."""
    if result is None:
        return ""
    if hasattr(result, "content") and result.content:
        for item in result.content:
            if hasattr(item, "text"):
                return item.text
    if hasattr(result, "text"):
        return result.text
    return str(result)
```

- [ ] **Step 4: 运行测试，确认通过**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core && python -m pytest tests/scene/test_http_sse.py -v
```

Expected: 7 个用例全部 PASS

---

## Task 3: 实现 manager.py（SessionManager）

**Files:**
- Create: `scene/http_sse/manager.py`
- Test: `tests/scene/test_http_sse.py`（追加 manager 测试）

- [ ] **Step 1: 写测试 — 验证 SessionManager 新建和复用**

在 `tests/scene/test_http_sse.py` 追加：

```python
import tempfile

import pytest

from scene.http_sse.manager import SessionManager


@pytest.fixture
def manager():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = SessionManager(cwd=tmpdir, session_store_dir=tmpdir)
        yield mgr


async def test_get_or_create_new_session(manager):
    session_id, assistant = await manager.get_or_create(None)
    assert session_id.startswith("scene-")
    assert assistant is not None


async def test_get_or_create_reuse(manager):
    sid1, assistant1 = await manager.get_or_create(None)
    sid2, assistant2 = await manager.get_or_create(sid1)
    assert sid1 == sid2
    assert assistant1 is assistant2
```

- [ ] **Step 2: 运行测试，确认失败**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core && python -m pytest tests/scene/test_http_sse.py::test_get_or_create_new_session tests/scene/test_http_sse.py::test_get_or_create_reuse -v
```

Expected: FAIL（`SessionManager` 未定义）

- [ ] **Step 3: 实现 `scene/http_sse/manager.py`**

创建 `/Users/yuanbaishu/pythonProject/agent-core/scene/http_sse/manager.py`，写入：

```python
"""Session manager for the HTTP SSE chat scene."""

from __future__ import annotations

import os
import time
from typing import Any

from agent_core.session.jsonl_store import JsonlStore
from agent_core.session.store import SessionStore

from scene.http_sse.chat_assistant import ChatAssistant


def _generate_session_id() -> str:
    return f"scene-{int(time.time() * 1000)}"


class SessionManager:
    """Manages ChatAssistant instances and their persistent storage."""

    def __init__(
        self,
        *,
        cwd: str = "",
        session_store_dir: str = "./sessions",
    ) -> None:
        self._cwd = cwd or os.getcwd()
        self._store_dir = session_store_dir
        self._sessions: dict[str, ChatAssistant] = {}

    async def get_or_create(self, session_id: str | None) -> tuple[str, ChatAssistant]:
        """Get an existing assistant or create a new one."""
        if session_id and session_id in self._sessions:
            return session_id, self._sessions[session_id]

        sid = session_id or _generate_session_id()
        store = JsonlStore(self._store_dir)
        assistant = await ChatAssistant.create(
            session_store=store,
            session_id=sid,
            cwd=self._cwd,
        )
        self._sessions[sid] = assistant
        return sid, assistant

    async def dispose(self, session_id: str) -> None:
        """Dispose a session and remove it from memory."""
        assistant = self._sessions.pop(session_id, None)
        if assistant:
            await assistant.dispose()

    async def dispose_all(self) -> None:
        """Dispose all active sessions."""
        for assistant in list(self._sessions.values()):
            await assistant.dispose()
        self._sessions.clear()
```

- [ ] **Step 4: 运行测试，确认通过**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core && python -m pytest tests/scene/test_http_sse.py -v
```

Expected: 9 个用例全部 PASS（7 events + 2 manager）

---

## Task 4: 实现 server.py（FastAPI 路由 + SSE 流）

**Files:**
- Create: `scene/http_sse/server.py`（覆盖现有占位文件）

- [ ] **Step 1: 创建 `scene/http_sse/server.py`**

覆盖写入：

```python
"""HTTP SSE chat assistant scene — FastAPI server."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from agent_core.core.events import AgentEvent

from scene.http_sse.events import agent_event_to_sse_json
from scene.http_sse.manager import SessionManager


class ChatRequest(BaseModel):
    message: str


manager = SessionManager(cwd=os.getcwd())


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await manager.dispose_all()


app = FastAPI(title="Agent Core HTTP SSE Chat", lifespan=lifespan)


def _format_sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def _event_stream(
    session_id: str | None,
    message: str,
) -> AsyncIterator[str]:
    """Yield SSE-formatted events for a chat turn."""
    sid, assistant = await manager.get_or_create(session_id)

    # Send session_id first
    yield _format_sse({"event": "session_id", "session_id": sid})

    queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

    def _handler(evt: AgentEvent) -> None:
        queue.put_nowait(evt)

    unsub = assistant.on_event(_handler)

    try:
        await assistant.send_message(message)
        # Wait until message_end arrives, then send done
        while True:
            evt = await asyncio.wait_for(queue.get(), timeout=300.0)
            if evt is None:
                break
            data = agent_event_to_sse_json(evt)
            if data is not None:
                yield _format_sse(data)
            if isinstance(evt, type(AgentEvent)) and getattr(evt, "type", None) == "message_end":
                break
    except asyncio.TimeoutError:
        yield _format_sse({"event": "error", "message": "Request timed out"})
    finally:
        unsub()
        yield _format_sse({"event": "done"})


@app.post("/chat/stream")
async def chat_stream(request: Request, chat_request: ChatRequest) -> StreamingResponse:
    session_id = request.query_params.get("session_id")
    return StreamingResponse(
        _event_stream(session_id, chat_request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/")
async def index() -> HTMLResponse:
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = _fallback_html()
    return HTMLResponse(content=content)


def _fallback_html() -> str:
    return """<!DOCTYPE html>
<html><head><title>Agent Core SSE Chat</title></head>
<body><h1>Chat Demo</h1><p>static/index.html not found</p></body></html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("scene.http_sse.server:app", host="0.0.0.0", port=8000, reload=False)
```

- [ ] **Step 2: 验证 import 烟测**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
python -c "from scene.http_sse.server import app; print('server import OK')"
```

Expected: `server import OK`

---

## Task 5: 实现 HTML demo 页面

**Files:**
- Create: `scene/http_sse/static/index.html`
- Create: `scene/http_sse/static/` 目录

- [ ] **Step 1: 创建 `scene/http_sse/static/` 目录**

```bash
mkdir -p /Users/yuanbaishu/pythonProject/agent-core/scene/http_sse/static
```

- [ ] **Step 2: 创建 `scene/http_sse/static/index.html`**

写入：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent Core SSE Chat</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        header {
            background: #1a1a2e;
            color: #fff;
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        header h1 { font-size: 1.2rem; }
        header button {
            background: #e94560;
            color: #fff;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            cursor: pointer;
        }
        header button:hover { background: #c73e54; }
        #chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 1rem 2rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }
        .message {
            max-width: 80%;
            padding: 0.75rem 1rem;
            border-radius: 12px;
            line-height: 1.5;
            word-wrap: break-word;
        }
        .message.user {
            align-self: flex-end;
            background: #0f3460;
            color: #fff;
        }
        .message.assistant {
            align-self: flex-start;
            background: #fff;
            color: #333;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .message.tool {
            align-self: flex-start;
            background: #fff3cd;
            color: #856404;
            font-family: monospace;
            font-size: 0.85rem;
        }
        .message .tool-name {
            font-weight: bold;
            margin-bottom: 0.25rem;
        }
        .message .tool-result {
            margin-top: 0.25rem;
            padding: 0.25rem;
            background: rgba(0,0,0,0.05);
            border-radius: 4px;
        }
        .message .tool-error {
            color: #dc3545;
        }
        #input-area {
            background: #fff;
            padding: 1rem 2rem;
            border-top: 1px solid #e0e0e0;
            display: flex;
            gap: 0.75rem;
        }
        #message-input {
            flex: 1;
            padding: 0.75rem 1rem;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 1rem;
            outline: none;
        }
        #message-input:focus { border-color: #0f3460; }
        #send-btn {
            background: #0f3460;
            color: #fff;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1rem;
        }
        #send-btn:hover { background: #1a4a7a; }
        #send-btn:disabled { background: #ccc; cursor: not-allowed; }
        .usage-info {
            font-size: 0.75rem;
            color: #888;
            margin-top: 0.5rem;
        }
    </style>
</head>
<body>
    <header>
        <h1>Agent Core SSE Chat</h1>
        <button id="new-session-btn">新会话</button>
    </header>
    <div id="chat-container"></div>
    <div id="input-area">
        <input type="text" id="message-input" placeholder="输入消息..." autocomplete="off">
        <button id="send-btn">发送</button>
    </div>

    <script>
        let sessionId = null;
        const chatContainer = document.getElementById('chat-container');
        const messageInput = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        const newSessionBtn = document.getElementById('new-session-btn');

        function addMessage(role, content) {
            const div = document.createElement('div');
            div.className = `message ${role}`;
            div.innerHTML = content;
            chatContainer.appendChild(div);
            chatContainer.scrollTop = chatContainer.scrollHeight;
            return div;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        async function sendMessage() {
            const text = messageInput.value.trim();
            if (!text) return;

            messageInput.value = '';
            addMessage('user', escapeHtml(text));
            sendBtn.disabled = true;

            const assistantMsg = addMessage('assistant', '<span class="cursor">...</span>');
            let currentText = '';
            let toolDiv = null;

            const url = new URL('/chat/stream', window.location.origin);
            if (sessionId) url.searchParams.set('session_id', sessionId);

            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text }),
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                const lines = buffer.split('\n\n');
                buffer = lines.pop() || '';

                for (const chunk of lines) {
                    const dataLine = chunk.split('\n').find(l => l.startsWith('data: '));
                    if (!dataLine) continue;
                    const data = JSON.parse(dataLine.slice(6));

                    if (data.event === 'session_id') {
                        sessionId = data.session_id;
                    } else if (data.event === 'text_delta') {
                        currentText += data.text;
                        assistantMsg.innerHTML = escapeHtml(currentText);
                    } else if (data.event === 'thinking_delta') {
                        // Silently ignore thinking content in UI
                    } else if (data.event === 'tool_start') {
                        toolDiv = addMessage('tool', `
                            <div class="tool-name">[Tool: ${escapeHtml(data.tool_name)}]</div>
                            <div>${escapeHtml(JSON.stringify(data.args))}</div>
                        `);
                    } else if (data.event === 'tool_end') {
                        if (toolDiv) {
                            const resultClass = data.is_error ? 'tool-error' : '';
                            toolDiv.innerHTML += `<div class="tool-result ${resultClass}">${escapeHtml(data.result)}</div>`;
                        }
                    } else if (data.event === 'message_end') {
                        if (data.usage) {
                            assistantMsg.innerHTML += `<div class="usage-info">Tokens: ${data.usage.input_tokens} in / ${data.usage.output_tokens} out (total ${data.usage.total_tokens})</div>`;
                        }
                    } else if (data.event === 'done') {
                        sendBtn.disabled = false;
                    }
                }
            }

            sendBtn.disabled = false;
        }

        sendBtn.addEventListener('click', sendMessage);
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });

        newSessionBtn.addEventListener('click', () => {
            sessionId = null;
            chatContainer.innerHTML = '';
        });
    </script>
</body>
</html>
```

- [ ] **Step 3: 验证文件存在**

Run:
```bash
cat /Users/yuanbaishu/pythonProject/agent-core/scene/http_sse/static/index.html | head -5
```

Expected: 显示 HTML 文件的开头几行

---

## Task 6: 运行验证

**Files:** (read-only verification)

- [ ] **Step 1: import 烟测**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
python -c "from scene.http_sse.server import app; from scene.http_sse.manager import SessionManager; from scene.http_sse.events import agent_event_to_sse_json; print('all imports OK')"
```

Expected: `all imports OK`

- [ ] **Step 2: 运行全部 http_sse 测试**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core && python -m pytest tests/scene/test_http_sse.py -v
```

Expected: 9 个用例全部 PASS

- [ ] **Step 3: 运行原有 scene 测试，确认无回归**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core && python -m pytest tests/scene/test_scene.py -v
```

Expected: 4 个用例全部 PASS

- [ ] **Step 4: 启动服务并做 curl 烟测（可选，需要 API key）**

启动（后台）：
```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
python -c "import uvicorn; uvicorn.run('scene.http_sse.server:app', host='127.0.0.1', port=8000, log_level='info')" &
```

Wait 2 seconds, then:
```bash
curl -s http://localhost:8000/ | head -1
```

Expected: `<!DOCTYPE html>`

终止后台服务：
```bash
pkill -f "uvicorn.run.*scene.http_sse.server" || true
```

---

## Task 7: 最终 cross-repo grep 复核

- [ ] **Step 1: 确认没有旧 import 残留**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
grep -rn "from scene\.chat_assistant\|from scene\.system_prompt" --include="*.py" .
```

Expected: 无输出（和目录重构完成后一致）

- [ ] **Step 2: 确认 http_sse 目录结构**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
find scene/http_sse -type f -name "*.py" -o -name "*.html" | sort
```

Expected：
```
scene/http_sse/__init__.py
scene/http_sse/chat_assistant.py
scene/http_sse/events.py
scene/http_sse/manager.py
scene/http_sse/server.py
scene/http_sse/static/index.html
scene/http_sse/system_prompt.py
```
