# Scene 目录重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `scene/` 从扁平布局重构为按场景分目录(`cli/` / `http_sse/` / `voice_ws/`),每个场景自包含,新增的两个场景仅留骨架。

**Architecture:** 现有 3 个 .py 文件迁入 `scene/cli/`,行为不变;为 `http_sse/` 和 `voice_ws/` 各复制一份 `chat_assistant.py` + `system_prompt.py`,并新建占位 `server.py`。所有引用旧路径的 import 同步修正。

**Tech Stack:** Python 3.11+,pytest;不引入新依赖。

**Spec:** `docs/superpowers/specs/2026-05-14-scene-restructure-design.md`

**Note:** 本仓库当前不是 git 仓库,实施步骤里不包含 `git add` / `git commit`;每个 Task 结尾用 import 烟测和(可选)pytest 作为验证。

---

## File Structure

**新建:**
- `scene/cli/__init__.py`
- `scene/http_sse/__init__.py`
- `scene/http_sse/chat_assistant.py`(从 cli 复制)
- `scene/http_sse/system_prompt.py`(从 cli 复制)
- `scene/http_sse/server.py`(占位)
- `scene/voice_ws/__init__.py`
- `scene/voice_ws/chat_assistant.py`(从 cli 复制)
- `scene/voice_ws/system_prompt.py`(从 cli 复制)
- `scene/voice_ws/server.py`(占位)

**移动:**
- `scene/chat_assistant.py` → `scene/cli/chat_assistant.py`
- `scene/system_prompt.py` → `scene/cli/system_prompt.py`
- `scene/cli.py` → `scene/cli/cli.py`

**修改:**
- `scene/__init__.py`:删除 re-export
- `scene/cli/chat_assistant.py`:`from scene.system_prompt` → `from scene.cli.system_prompt`
- `scene/cli/cli.py`:`from scene.chat_assistant` → `from scene.cli.chat_assistant`
- `scene/http_sse/chat_assistant.py`:`from scene.system_prompt` → `from scene.http_sse.system_prompt`
- `scene/voice_ws/chat_assistant.py`:`from scene.system_prompt` → `from scene.voice_ws.system_prompt`
- `tests/scene/test_scene.py`:两处 import 改向 `scene.cli.*`
- `tests/scene/test_minimax_e2e.py`:一处 import 改向 `scene.cli.*`

---

## Task 1: 把现有 CLI 场景迁入 `scene/cli/`

**Files:**
- Create: `scene/cli/__init__.py`
- Move: `scene/chat_assistant.py` → `scene/cli/chat_assistant.py`
- Move: `scene/system_prompt.py` → `scene/cli/system_prompt.py`
- Move: `scene/cli.py` → `scene/cli/cli.py`
- Modify: `scene/__init__.py`
- Modify: `scene/cli/chat_assistant.py:36`(import 修正)
- Modify: `scene/cli/cli.py:25`(import 修正)
- Modify: `tests/scene/test_scene.py:9-10`(import 修正)
- Modify: `tests/scene/test_minimax_e2e.py:22`(import 修正)

- [ ] **Step 1: 跑 baseline 测试,确认改动前测试通过**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && python -m pytest tests/scene/test_scene.py -v
```

Expected: 4 个用例全部 PASS(`test_build_system_prompt`、`test_build_system_prompt_with_skills`、`test_chat_assistant_expand_skill_command`、`test_chat_assistant_expand_unknown_skill`)。
如有 FAIL,先解决环境问题,再继续。

- [ ] **Step 2: 创建 `scene/cli/` 目录**

Run:

```bash
mkdir -p /Users/yuanbaishu/pythonProject/agent-core/scene/cli
```

- [ ] **Step 3: 创建 `scene/cli/__init__.py`**

写入:

```python
"""Terminal CLI scene for the chat assistant."""
```

- [ ] **Step 4: 把现有 3 个文件移入 `scene/cli/`**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
mv scene/chat_assistant.py scene/cli/chat_assistant.py && \
mv scene/system_prompt.py scene/cli/system_prompt.py && \
mv scene/cli.py scene/cli/cli.py
```

- [ ] **Step 5: 修正 `scene/cli/chat_assistant.py` 中的 import**

找到原第 36 行:

```python
from scene.system_prompt import build_system_prompt
```

替换为:

```python
from scene.cli.system_prompt import build_system_prompt
```

- [ ] **Step 6: 修正 `scene/cli/cli.py` 中的 import**

找到原第 25 行:

```python
from scene.chat_assistant import ChatAssistant
```

替换为:

```python
from scene.cli.chat_assistant import ChatAssistant
```

- [ ] **Step 7: 改写 `scene/__init__.py`,移除 re-export**

整个文件覆盖为:

```python
"""Scene — adapters wrapping agent_core for different runtime surfaces."""
```

- [ ] **Step 8: 修正 `tests/scene/test_scene.py` 的 import**

找到第 9-10 行:

```python
from scene.chat_assistant import ChatAssistant
from scene.system_prompt import build_system_prompt
```

替换为:

```python
from scene.cli.chat_assistant import ChatAssistant
from scene.cli.system_prompt import build_system_prompt
```

- [ ] **Step 9: 修正 `tests/scene/test_minimax_e2e.py` 的 import**

找到第 22 行:

```python
from scene.chat_assistant import ChatAssistant
```

替换为:

```python
from scene.cli.chat_assistant import ChatAssistant
```

- [ ] **Step 10: 清理 pyc 缓存,避免旧路径残留**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
find scene tests/scene -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; true
```

- [ ] **Step 11: 跑回归测试,确认行为不变**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && python -m pytest tests/scene/test_scene.py -v
```

Expected: 与 Step 1 完全相同的 4 个用例 PASS。任何 FAIL 都意味着上面 step 漏了什么。

- [ ] **Step 12: import 烟测,验证 cli scene 入口可解析**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
python -c "from scene.cli.chat_assistant import ChatAssistant; from scene.cli.system_prompt import build_system_prompt; from scene.cli import cli; print('cli scene OK')"
```

Expected: 打印 `cli scene OK`,无 ImportError。

---

## Task 2: 创建 `scene/http_sse/` 骨架

**Files:**
- Create: `scene/http_sse/__init__.py`
- Create: `scene/http_sse/chat_assistant.py`(从 cli 复制)
- Create: `scene/http_sse/system_prompt.py`(从 cli 复制)
- Create: `scene/http_sse/server.py`(占位)
- Modify: `scene/http_sse/chat_assistant.py`(import 改向本场景)

- [ ] **Step 1: 创建 `scene/http_sse/` 目录**

Run:

```bash
mkdir -p /Users/yuanbaishu/pythonProject/agent-core/scene/http_sse
```

- [ ] **Step 2: 创建 `scene/http_sse/__init__.py`**

写入:

```python
"""HTTP SSE chat assistant scene."""
```

- [ ] **Step 3: 复制 chat_assistant.py 和 system_prompt.py**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
cp scene/cli/chat_assistant.py scene/http_sse/chat_assistant.py && \
cp scene/cli/system_prompt.py scene/http_sse/system_prompt.py
```

- [ ] **Step 4: 修正 `scene/http_sse/chat_assistant.py` 的 import**

找到这行(复制后位置与 Task 1 Step 5 之后一致):

```python
from scene.cli.system_prompt import build_system_prompt
```

替换为:

```python
from scene.http_sse.system_prompt import build_system_prompt
```

- [ ] **Step 5: 创建占位 `scene/http_sse/server.py`**

写入:

```python
"""HTTP SSE chat assistant scene — server entry point.

TODO: implement FastAPI / Starlette app exposing the chat assistant
over Server-Sent Events (text/event-stream).
"""
```

- [ ] **Step 6: import 烟测**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
python -c "from scene.http_sse.chat_assistant import ChatAssistant; from scene.http_sse.system_prompt import build_system_prompt; import scene.http_sse.server; print('http_sse scene OK')"
```

Expected: 打印 `http_sse scene OK`,无 ImportError。

---

## Task 3: 创建 `scene/voice_ws/` 骨架

**Files:**
- Create: `scene/voice_ws/__init__.py`
- Create: `scene/voice_ws/chat_assistant.py`(从 cli 复制)
- Create: `scene/voice_ws/system_prompt.py`(从 cli 复制)
- Create: `scene/voice_ws/server.py`(占位)
- Modify: `scene/voice_ws/chat_assistant.py`(import 改向本场景)

- [ ] **Step 1: 创建 `scene/voice_ws/` 目录**

Run:

```bash
mkdir -p /Users/yuanbaishu/pythonProject/agent-core/scene/voice_ws
```

- [ ] **Step 2: 创建 `scene/voice_ws/__init__.py`**

写入:

```python
"""WebSocket voice-call scene."""
```

- [ ] **Step 3: 复制 chat_assistant.py 和 system_prompt.py**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
cp scene/cli/chat_assistant.py scene/voice_ws/chat_assistant.py && \
cp scene/cli/system_prompt.py scene/voice_ws/system_prompt.py
```

- [ ] **Step 4: 修正 `scene/voice_ws/chat_assistant.py` 的 import**

找到这行:

```python
from scene.cli.system_prompt import build_system_prompt
```

替换为:

```python
from scene.voice_ws.system_prompt import build_system_prompt
```

- [ ] **Step 5: 创建占位 `scene/voice_ws/server.py`**

写入:

```python
"""WebSocket voice-call scene — server entry point.

TODO: implement WebSocket handler bridging audio frames (ASR/TTS)
to the chat assistant agent loop.
"""
```

- [ ] **Step 6: import 烟测**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
python -c "from scene.voice_ws.chat_assistant import ChatAssistant; from scene.voice_ws.system_prompt import build_system_prompt; import scene.voice_ws.server; print('voice_ws scene OK')"
```

Expected: 打印 `voice_ws scene OK`,无 ImportError。

---

## Task 4: 全仓 grep 复核,确认无遗漏

**Files:** (read-only verification)

- [ ] **Step 1: grep `from scene.chat_assistant`**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
grep -rn "from scene\.chat_assistant" --include="*.py" .
```

Expected: 无任何输出。任何命中都意味着遗漏的引用,补改之。

- [ ] **Step 2: grep `from scene.system_prompt`**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
grep -rn "from scene\.system_prompt" --include="*.py" .
```

Expected: 无任何输出。

- [ ] **Step 3: 最终结构核对**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
find scene -type f -name "*.py" | sort
```

Expected 输出(顺序可能略不同,但列表必须一致):

```
scene/__init__.py
scene/cli/__init__.py
scene/cli/chat_assistant.py
scene/cli/cli.py
scene/cli/system_prompt.py
scene/http_sse/__init__.py
scene/http_sse/chat_assistant.py
scene/http_sse/server.py
scene/http_sse/system_prompt.py
scene/voice_ws/__init__.py
scene/voice_ws/chat_assistant.py
scene/voice_ws/server.py
scene/voice_ws/system_prompt.py
```

- [ ] **Step 4: 完整跑 scene 测试**

Run:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && python -m pytest tests/scene/test_scene.py -v
```

Expected: 与 Task 1 Step 1 baseline 相同的 4 个用例 PASS。

Note: `tests/scene/test_minimax_e2e.py` 需要 `MINIMAX_API_KEY`,**不在本计划的验证范围内**;只要它的 import 能 parse 即可:

```bash
cd /Users/yuanbaishu/pythonProject/agent-core && \
python -c "import ast; ast.parse(open('tests/scene/test_minimax_e2e.py').read()); print('test_minimax_e2e parse OK')"
```

Expected: 打印 `test_minimax_e2e parse OK`。
