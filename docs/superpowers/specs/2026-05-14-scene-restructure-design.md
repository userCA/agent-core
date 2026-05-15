# Scene 目录重构 + 新增 HTTP SSE / WebSocket 语音场景骨架

> 日期:2026-05-14
> 范围:仅目录骨架(不实现 SSE / WebSocket 业务逻辑)

---

## 1. 背景

当前 `scene/` 是扁平布局,只包含一个终端 CLI 场景:

```
scene/
├── __init__.py
├── chat_assistant.py
├── cli.py
└── system_prompt.py
```

随后需要支持多个独立场景(HTTP SSE 聊天助手、WebSocket 语音通话),
扁平布局无法容纳多个场景。本任务把目录整理为多场景子目录布局,
并为两个新场景搭好骨架。

## 2. 目标

- 把 `scene/` 改为按场景分目录的布局,每个场景自包含。
- 把现有 CLI 场景代码原样迁入 `scene/cli/`,行为不变。
- 新增 `scene/http_sse/` 与 `scene/voice_ws/` 两个场景骨架。
- 修复所有受影响的 import(scene 内部 + tests)。

## 3. 非目标 (YAGNI)

- 不实现 HTTP SSE 服务端逻辑,`http_sse/server.py` 只是占位。
- 不实现 WebSocket 语音管道(ASR/TTS/帧编码),`voice_ws/server.py` 只是占位。
- 不抽出 `common/` 共享层。三个场景各自持有一份 `chat_assistant.py` /
  `system_prompt.py`,允许后续独立演化。
- 不改动 `agent_core/` 任何模块。
- 不新增 runtime 依赖(FastAPI / Starlette / WebSocket / 音频库等)。

## 4. 目标结构

```
scene/
├── __init__.py            # 空模块(docstring),不再 re-export
├── cli/                   # 终端 CLI 场景(现有代码迁入)
│   ├── __init__.py
│   ├── chat_assistant.py
│   ├── system_prompt.py
│   └── cli.py
├── http_sse/              # HTTP SSE 聊天助手场景(新)
│   ├── __init__.py
│   ├── chat_assistant.py  # 从 cli 复制,作为起点
│   ├── system_prompt.py   # 从 cli 复制,作为起点
│   └── server.py          # 占位:docstring + TODO 注释
└── voice_ws/              # WebSocket 语音通话场景(新)
    ├── __init__.py
    ├── chat_assistant.py  # 从 cli 复制,作为起点
    ├── system_prompt.py   # 从 cli 复制,作为起点
    └── server.py          # 占位:docstring + TODO 注释
```

### 各场景边界

- **cli/**:终端交互式输入 + 流式打印 + JSONL 会话存储。当前实现保持不变。
- **http_sse/**:未来承载基于 HTTP Server-Sent Events 的聊天接口
  (例如 FastAPI + `text/event-stream` 流式响应)。本次只留骨架。
- **voice_ws/**:未来承载基于 WebSocket 的双向语音通话
  (音频上行 → ASR → Agent → TTS → 音频下行)。本次只留骨架。

## 5. 改动清单

### 5.1 文件移动 / 复制

| 操作 | 源 | 目标 |
|---|---|---|
| 移动 | `scene/chat_assistant.py` | `scene/cli/chat_assistant.py` |
| 移动 | `scene/system_prompt.py` | `scene/cli/system_prompt.py` |
| 移动 | `scene/cli.py` | `scene/cli/cli.py` |
| 复制 | `scene/cli/chat_assistant.py` | `scene/http_sse/chat_assistant.py` |
| 复制 | `scene/cli/system_prompt.py` | `scene/http_sse/system_prompt.py` |
| 复制 | `scene/cli/chat_assistant.py` | `scene/voice_ws/chat_assistant.py` |
| 复制 | `scene/cli/system_prompt.py` | `scene/voice_ws/system_prompt.py` |
| 新建 | — | `scene/cli/__init__.py`(空) |
| 新建 | — | `scene/http_sse/__init__.py`(空) |
| 新建 | — | `scene/http_sse/server.py`(占位) |
| 新建 | — | `scene/voice_ws/__init__.py`(空) |
| 新建 | — | `scene/voice_ws/server.py`(占位) |

### 5.2 Import 修改

**`scene/__init__.py`**:

去掉 `ChatAssistant` 和 `build_system_prompt` 的 re-export。
保留模块 docstring。

**`scene/cli/chat_assistant.py`**:

```python
# 旧
from scene.system_prompt import build_system_prompt
# 新
from scene.cli.system_prompt import build_system_prompt
```

**`scene/cli/cli.py`**:

```python
# 旧
from scene.chat_assistant import ChatAssistant
# 新
from scene.cli.chat_assistant import ChatAssistant
```

**`scene/http_sse/chat_assistant.py`**:

```python
# 复制自 cli,改为
from scene.http_sse.system_prompt import build_system_prompt
```

**`scene/voice_ws/chat_assistant.py`**:

```python
# 复制自 cli,改为
from scene.voice_ws.system_prompt import build_system_prompt
```

**`tests/scene/test_scene.py`**:

```python
# 旧
from scene.chat_assistant import ChatAssistant
from scene.system_prompt import build_system_prompt
# 新
from scene.cli.chat_assistant import ChatAssistant
from scene.cli.system_prompt import build_system_prompt
```

**`tests/scene/test_minimax_e2e.py`**:

```python
# 旧
from scene.chat_assistant import ChatAssistant
# 新
from scene.cli.chat_assistant import ChatAssistant
```

### 5.3 占位文件内容

**`scene/http_sse/server.py`**:

```python
"""HTTP SSE chat assistant scene — server entry point.

TODO: implement FastAPI / Starlette app exposing the chat assistant
over Server-Sent Events (text/event-stream).
"""
```

**`scene/voice_ws/server.py`**:

```python
"""WebSocket voice-call scene — server entry point.

TODO: implement WebSocket handler bridging audio frames (ASR/TTS)
to the chat assistant agent loop.
"""
```

**`scene/__init__.py`**:

```python
"""Scene — adapters wrapping agent_core for different runtime surfaces."""
```

**`scene/cli/__init__.py`**, **`scene/http_sse/__init__.py`**,
**`scene/voice_ws/__init__.py`**:空文件(或仅一行 docstring,描述本场景)。

## 6. 验证

- `python -c "from scene.cli.chat_assistant import ChatAssistant"` 成功。
- `python -c "from scene.cli.cli import main"`(或对应入口)能解析,
  与改动前等价。
- `pytest tests/scene` 全部通过(若环境允许跑)。
- 仓库中除 `tests/scene/` 与 `scene/` 之外无其他文件引用旧路径
  (可用 `grep -r "from scene\." --include="*.py"` 复核)。

## 7. 风险与回退

- 风险点:scene/__init__.py 的 re-export 被外部代码依赖。已通过 grep
  确认目前仅 `tests/scene/` 和 `scene/` 自身使用,无外部依赖。
- 回退方式:`git revert` 单个重构 commit 即可恢复扁平布局。
