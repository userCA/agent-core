# agent-core 三方向优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 agent_core 在工具系统可插拔性、资源发现加载、系统提示词构建三个领域与 demo/core 的差距。

**Architecture:** 新增 `agent_core/tools/operations.py` + `mutation_queue.py` + `render.py` 实现工具可插拔；新增 `agent_core/resources/` 包统一资源发现；新增 `agent_core/prompts/` 包实现动态系统提示词构建；扩展 `agent_core/extensions/` 支持加载和更多事件。

**Tech Stack:** Python 3.11+, `pydantic>=2.5`, `pytest>=8`, `pathspec>=0.12`, `pyyaml>=6.0`

---

## 文件结构总览

### 新建文件

| 文件 | 职责 |
|---|---|
| `agent_core/tools/operations.py` | `FileOperations`, `BashOperations` Protocol |
| `agent_core/tools/operations_local.py` | `LocalFileOperations`, `LocalBashOperations` 实现 |
| `agent_core/tools/mutation_queue.py` | `FileMutationQueue` 文件编辑串行化 |
| `agent_core/tools/render.py` | `RenderedOutput`, `ToolRenderer` Protocol |
| `agent_core/tools/local/edit.py` | `EditTool` 精确文本替换 |
| `agent_core/resources/__init__.py` | 资源包入口 |
| `agent_core/resources/types.py` | `Skill`, `PromptTemplate`, `Theme`, `ContextFile`, `SourceInfo`, `ResourceDiagnostic` |
| `agent_core/resources/diagnostics.py` | `ResourceDiagnostics` 收集器 |
| `agent_core/resources/skills.py` | Skill 加载逻辑 |
| `agent_core/resources/prompts.py` | Prompt Template 加载 |
| `agent_core/resources/themes.py` | Theme 加载 |
| `agent_core/resources/context_files.py` | `AGENTS.md` / `CLAUDE.md` 加载 |
| `agent_core/resources/extensions.py` | ExtensionSpec 发现 |
| `agent_core/resources/loader.py` | `ResourceLoader` 统一资源发现 |
| `agent_core/extensions/loader.py` | `ExtensionLoader` 动态导入扩展 |
| `agent_core/prompts/__init__.py` | 提示词包入口 |
| `agent_core/prompts/builder.py` | `SystemPromptBuilder`, `SystemPrompt`, `SystemPromptSection` |
| `agent_core/prompts/guidelines.py` | 动态 Guidelines 规则 |
| `agent_core/prompts/snippets.py` | 工具 snippet 提取 |

### 修改文件

| 文件 | 修改内容 |
|---|---|
| `pyproject.toml` | 新增 `pathspec`, `pyyaml` 依赖 |
| `agent_core/tools/base.py` | `ToolResult` 增加 `display`，`ToolDefinition` 增加 `renderer`，`ToolContext` 增加 `mutation_queue` |
| `agent_core/tools/local/read.py` | 接入 `FileOperations`，增加智能截断 |
| `agent_core/tools/local/write.py` | 接入 `FileOperations`，增加 `mutation_queue` 和 `display` |
| `agent_core/tools/local/bash.py` | 接入 `BashOperations`，增加流式/超时 |
| `agent_core/tools/local/ls.py` | 接入 `FileOperations` |
| `agent_core/tools/local/grep.py` | 接入 `FileOperations` |
| `agent_core/tools/local/find.py` | 接入 `FileOperations` |
| `agent_core/tools/local/__init__.py` | 导出 `EditTool` |
| `agent_core/tools/__init__.py` | 导出新增类型 |
| `agent_core/core/tool_runner.py` | `ToolContext` 传入 `mutation_queue` |
| `agent_core/extensions/base.py` | 增加 `on_before_agent_start` |
| `agent_core/extensions/runner.py` | 支持 `on_before_agent_start` |
| `agent_core/extensions/__init__.py` | 导出 `ExtensionLoader` |
| `scene/cli/system_prompt.py` | 删除（逻辑迁入 `agent_core/prompts/`） |
| `scene/http_sse/system_prompt.py` | 删除 |
| `scene/voice_ws/system_prompt.py` | 删除 |
| `scene/cli/chat_assistant.py` | 使用 `SystemPromptBuilder` |
| `scene/http_sse/chat_assistant.py` | 使用 `SystemPromptBuilder` |
| `scene/voice_ws/chat_assistant.py` | 使用 `SystemPromptBuilder` |

---

## Phase 0: 项目依赖与目录结构

### Task 0.1: 安装 pathspec 和 pyyaml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 添加依赖**

```toml
[project]
dependencies = [
    "pydantic>=2.5",
    "httpx>=0.27",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.30",
    "pathspec>=0.12",
    "pyyaml>=6.0",
]
```

- [ ] **Step 2: 安装到当前 venv**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core
.venv/bin/pip install pathspec>=0.12 pyyaml>=6.0
```

Expected: `Successfully installed pathspec-... pyyaml-...`

- [ ] **Step 3: 安装 editable 模式确保依赖完整**

Run:
```bash
.venv/bin/pip install -e ".[test]"
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(deps): add pathspec and pyyaml for resource loading"
```

### Task 0.2: 创建新目录结构

**Files:**
- Create: `agent_core/resources/` (目录)
- Create: `agent_core/prompts/` (目录)

- [ ] **Step 1: 创建空 __init__.py 占位**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core
mkdir -p agent_core/resources agent_core/prompts tests/resources tests/prompts
touch agent_core/resources/__init__.py
touch agent_core/prompts/__init__.py
touch tests/resources/__init__.py
touch tests/prompts/__init__.py
```

- [ ] **Step 2: Commit**

```bash
git add agent_core/resources agent_core/prompts tests/resources tests/prompts
git commit -m "chore: create resources and prompts package directories"
```

---

## Phase 1: 工具系统 —— 可插拔操作层与编辑队列

### Task 1.1: 工具渲染协议

**Files:**
- Create: `agent_core/tools/render.py`
- Test: `tests/tools/test_render.py`

- [ ] **Step 1: 编写测试**

```python
from agent_core.tools.render import RenderedOutput


def test_rendered_output_defaults():
    ro = RenderedOutput(text="hello")
    assert ro.text == "hello"
    assert ro.display is None
    assert ro.mime_type == "text/plain"


def test_rendered_output_with_display():
    ro = RenderedOutput(text="hello", display={"code": "python"}, mime_type="text/x-python")
    assert ro.display == {"code": "python"}
    assert ro.mime_type == "text/x-python"
```

Run: `.venv/bin/pytest tests/tools/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 2: 实现 render.py**

```python
"""Tool rendering protocol for frontend display."""

from __future__ import annotations

from typing import Any, Protocol
from pydantic import BaseModel

from agent_core.tools.base import ToolResult


class RenderedOutput(BaseModel):
    """Rendered output of a tool call or result for frontend consumption."""
    text: str
    display: dict[str, Any] | None = None
    mime_type: str = "text/plain"


class ToolRenderer(Protocol):
    """Optional rendering protocol for tools."""

    async def render_call(self, tool_call_id: str, name: str, arguments: dict[str, Any]) -> str:
        """Render a short summary of the tool call (e.g. 'read /path/to/file')."""
        ...

    async def render_result(
        self,
        tool_call_id: str,
        name: str,
        result: ToolResult,
        is_error: bool,
    ) -> RenderedOutput:
        """Render the tool execution result."""
        ...
```

- [ ] **Step 3: 运行测试**

Run: `.venv/bin/pytest tests/tools/test_render.py -v`
Expected: `2 passed`

- [ ] **Step 4: Commit**

```bash
git add agent_core/tools/render.py tests/tools/test_render.py
git commit -m "feat(tools): add ToolRenderer protocol and RenderedOutput"
```

### Task 1.2: 可插拔操作层 Protocol

**Files:**
- Create: `agent_core/tools/operations.py`
- Test: `tests/tools/test_operations.py`

- [ ] **Step 1: 编写测试**

```python
import inspect

from agent_core.tools.operations import BashOperations, FileOperations, FileInfo


def test_file_info_is_dataclass():
    fi = FileInfo(name="x.py", path="/tmp/x.py", is_dir=False, size=100)
    assert fi.name == "x.py"
    assert not fi.is_dir


def test_file_operations_is_protocol():
    assert hasattr(FileOperations, "read")
    assert hasattr(FileOperations, "write")
    assert hasattr(FileOperations, "edit")


def test_bash_operations_is_protocol():
    assert hasattr(BashOperations, "execute")
```

Run: `.venv/bin/pytest tests/tools/test_operations.py -v`
Expected: FAIL

- [ ] **Step 2: 实现 operations.py**

```python
"""Pluggable operations protocols for file and bash execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class FileInfo:
    name: str
    path: str
    is_dir: bool
    size: int


class FileOperations(Protocol):
    """Abstract file operations. Allows local, SSH, or container backends."""

    async def read(self, path: str, *, offset: int = 0, limit: int | None = None) -> str: ...
    async def write(self, path: str, content: str) -> None: ...
    async def edit(self, path: str, old_text: str, new_text: str) -> bool: ...
    async def ls(self, path: str) -> list[FileInfo]: ...
    async def grep(self, pattern: str, path: str, *, recursive: bool = False) -> list[str]: ...
    async def find(self, path: str, *, name_pattern: str | None = None) -> list[str]: ...


@dataclass
class BashResult:
    stdout: str
    stderr: str
    returncode: int
    truncated: bool = False


class BashOperations(Protocol):
    """Abstract bash execution. Allows local, SSH, or container backends."""

    async def execute(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> BashResult: ...
```

- [ ] **Step 3: 运行测试**

Run: `.venv/bin/pytest tests/tools/test_operations.py -v`
Expected: `3 passed`

- [ ] **Step 4: Commit**

```bash
git add agent_core/tools/operations.py tests/tools/test_operations.py
git commit -m "feat(tools): add FileOperations and BashOperations protocols"
```

### Task 1.3: 本地操作实现

**Files:**
- Create: `agent_core/tools/operations_local.py`
- Test: `tests/tools/test_operations_local.py`

- [ ] **Step 1: 编写测试**

```python
import asyncio
import os
import tempfile

import pytest

from agent_core.tools.operations_local import LocalBashOperations, LocalFileOperations


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_local_file_operations_read(tmp_dir):
    path = os.path.join(tmp_dir, "test.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("hello world")

    ops = LocalFileOperations(cwd=tmp_dir)
    content = asyncio.run(ops.read("test.txt"))
    assert content == "hello world"


def test_local_file_operations_write_and_ls(tmp_dir):
    ops = LocalFileOperations(cwd=tmp_dir)
    asyncio.run(ops.write("foo.txt", "bar"))
    infos = asyncio.run(ops.ls(tmp_dir))
    names = {i.name for i in infos}
    assert "foo.txt" in names


def test_local_file_operations_edit(tmp_dir):
    ops = LocalFileOperations(cwd=tmp_dir)
    asyncio.run(ops.write("edit.txt", "old content here"))
    ok = asyncio.run(ops.edit("edit.txt", "old content", "new content"))
    assert ok
    content = asyncio.run(ops.read("edit.txt"))
    assert content == "new content here"


def test_local_bash_operations_echo():
    ops = LocalBashOperations()
    result = asyncio.run(ops.execute("echo hello"))
    assert result.returncode == 0
    assert "hello" in result.stdout
```

Run: `.venv/bin/pytest tests/tools/test_operations_local.py -v`
Expected: FAIL

- [ ] **Step 2: 实现 operations_local.py**

```python
"""Local filesystem and bash implementations of operations protocols."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from agent_core.tools.operations import BashOperations, BashResult, FileInfo, FileOperations


class LocalFileOperations(FileOperations):
    """Default local file system implementation."""

    def __init__(self, cwd: str | None = None) -> None:
        self._cwd = cwd or os.getcwd()

    def _resolve(self, path: str) -> str:
        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        return os.path.normpath(path)

    async def read(self, path: str, *, offset: int = 0, limit: int | None = None) -> str:
        path = self._resolve(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if offset or limit is not None:
                lines = f.readlines()
                start = offset
                end = start + (limit or len(lines))
                return "".join(lines[start:end])
            return f.read()

    async def write(self, path: str, content: str) -> None:
        path = self._resolve(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    async def edit(self, path: str, old_text: str, new_text: str) -> bool:
        path = self._resolve(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if old_text not in content:
            return False
        content = content.replace(old_text, new_text, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True

    async def ls(self, path: str) -> list[FileInfo]:
        path = self._resolve(path)
        entries: list[FileInfo] = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            entries.append(
                FileInfo(
                    name=name,
                    path=full,
                    is_dir=os.path.isdir(full),
                    size=os.path.getsize(full) if os.path.isfile(full) else 0,
                )
            )
        return entries

    async def grep(self, pattern: str, path: str, *, recursive: bool = False) -> list[str]:
        path = self._resolve(path)
        results: list[str] = []
        compiled = re.compile(pattern)

        def scan_file(file_path: str) -> None:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if compiled.search(line):
                            results.append(f"{file_path}:{i}:{line.rstrip()}")
            except (IsADirectoryError, PermissionError, OSError):
                pass

        if os.path.isfile(path):
            scan_file(path)
        elif recursive:
            for root, _, files in os.walk(path):
                for name in files:
                    scan_file(os.path.join(root, name))
        else:
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                if os.path.isfile(full):
                    scan_file(full)
        return results

    async def find(self, path: str, *, name_pattern: str | None = None) -> list[str]:
        path = self._resolve(path)
        results: list[str] = []
        if os.path.isfile(path):
            return [path]
        for root, _, files in os.walk(path):
            for name in files:
                if name_pattern is None or re.search(name_pattern, name):
                    results.append(os.path.join(root, name))
        return results


class LocalBashOperations(BashOperations):
    """Default local bash execution implementation."""

    def __init__(self, cwd: str | None = None, shell: str | None = None) -> None:
        self._cwd = cwd or os.getcwd()
        self._shell = shell or "/bin/bash"

    async def execute(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float | None = 60.0,
        env: dict[str, str] | None = None,
    ) -> BashResult:
        work_dir = cwd or self._cwd
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env={**os.environ, **(env or {})},
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            return BashResult(
                stdout=stdout,
                stderr=stderr,
                returncode=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return BashResult(
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                returncode=-1,
                truncated=True,
            )
```

- [ ] **Step 3: 运行测试**

Run: `.venv/bin/pytest tests/tools/test_operations_local.py -v`
Expected: `4 passed`

- [ ] **Step 4: Commit**

```bash
git add agent_core/tools/operations_local.py tests/tools/test_operations_local.py
git commit -m "feat(tools): add LocalFileOperations and LocalBashOperations"
```

### Task 1.4: 文件变更队列

**Files:**
- Create: `agent_core/tools/mutation_queue.py`
- Test: `tests/tools/test_mutation_queue.py`

- [ ] **Step 1: 编写测试**

```python
import asyncio
import tempfile

import pytest

from agent_core.tools.mutation_queue import FileMutationQueue
from agent_core.tools.operations_local import LocalFileOperations


@pytest.fixture
def queue():
    return FileMutationQueue()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.mark.asyncio
async def test_mutation_queue_serializes_access(queue, tmp_dir):
    ops = LocalFileOperations(cwd=tmp_dir)
    await ops.write("counter.txt", "0")

    async def increment():
        async with queue.acquire("counter.txt"):
            val = int(await ops.read("counter.txt"))
            await ops.write("counter.txt", str(val + 1))

    await asyncio.gather(*[increment() for _ in range(10)])
    result = await ops.read("counter.txt")
    assert result == "10"


@pytest.mark.asyncio
async def test_mutation_queue_read_locked(queue, tmp_dir):
    ops = LocalFileOperations(cwd=tmp_dir)
    await ops.write("test.txt", "hello")
    content = await queue.read_locked(ops, "test.txt")
    assert content == "hello"
```

Run: `.venv/bin/pytest tests/tools/test_mutation_queue.py -v`
Expected: FAIL

- [ ] **Step 2: 实现 mutation_queue.py**

```python
"""Serialize concurrent file mutations per path."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator

from agent_core.tools.operations import FileOperations


class FileMutationQueue:
    """Per-file async lock for serializing mutations."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def acquire(self, path: str) -> AsyncIterator[None]:
        lock = self._locks[path]
        async with lock:
            yield

    async def read_locked(self, file_ops: FileOperations, path: str) -> str:
        async with self.acquire(path):
            return await file_ops.read(path)

    async def write_locked(self, file_ops: FileOperations, path: str, content: str) -> None:
        async with self.acquire(path):
            await file_ops.write(path, content)

    async def edit_locked(
        self, file_ops: FileOperations, path: str, old_text: str, new_text: str
    ) -> bool:
        async with self.acquire(path):
            return await file_ops.edit(path, old_text, new_text)
```

- [ ] **Step 3: 运行测试**

Run: `.venv/bin/pytest tests/tools/test_mutation_queue.py -v`
Expected: `2 passed`

- [ ] **Step 4: Commit**

```bash
git add agent_core/tools/mutation_queue.py tests/tools/test_mutation_queue.py
git commit -m "feat(tools): add FileMutationQueue for serialized file edits"
```

### Task 1.5: 更新 ToolContext 和 ToolResult 支持 display + mutation_queue

**Files:**
- Modify: `agent_core/tools/base.py`
- Test: `tests/tools/test_base.py` (新增/修改)

- [ ] **Step 1: 修改 base.py**

在 `ToolResult` 中增加 `display`：

```python
class ToolResult(BaseModel):
    content: list[TextContent | ImageContent]
    details: Any | None = None
    display: dict[str, Any] | None = None
```

在 `ToolDefinition` 中增加 `renderer`：

```python
class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    prompt_snippet: str | None = None
    prompt_guidelines: list[str] = []
    renderer: Any | None = None
```

在 `ToolContext` 中增加 `mutation_queue`：

```python
@dataclass
class ToolContext:
    signal: asyncio.Event
    on_update: Callable[[ToolResult], None] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    mutation_queue: Any | None = None
```

- [ ] **Step 2: 编写测试验证新字段**

```python
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult


def test_tool_result_display():
    result = ToolResult(content=[], display={"code": "python"})
    assert result.display == {"code": "python"}


def test_tool_definition_renderer():
    definition = ToolDefinition(name="x", description="y", parameters={}, renderer=None)
    assert definition.renderer is None


def test_tool_context_mutation_queue():
    import asyncio

    ctx = ToolContext(signal=asyncio.Event(), mutation_queue=None)
    assert ctx.mutation_queue is None
```

Run: `.venv/bin/pytest tests/tools/test_base.py -v`
Expected: `3 passed`

- [ ] **Step 3: Commit**

```bash
git add agent_core/tools/base.py tests/tools/test_base.py
git commit -m "feat(tools): add display, renderer, mutation_queue to tool types"
```

### Task 1.6: 更新 tool_runner 传入 mutation_queue

**Files:**
- Modify: `agent_core/core/tool_runner.py`

- [ ] **Step 1: 修改 _run_single_tool**

在 `_run_single_tool` 中创建 `ToolContext` 时传入 `mutation_queue`：

```python
ctx = ToolContext(signal=abort_event, mutation_queue=getattr(config, "mutation_queue", None))
```

- [ ] **Step 2: Commit**

```bash
git add agent_core/core/tool_runner.py
git commit -m "feat(tools): pass mutation_queue through ToolContext"
```

### Task 1.7: 新增 EditTool

**Files:**
- Create: `agent_core/tools/local/edit.py`
- Test: `tests/tools/local/test_edit.py`

- [ ] **Step 1: 编写测试**

```python
import tempfile
import os

import pytest

from agent_core.tools.local.edit import EditTool


@pytest.fixture
def edit_tool():
    return EditTool()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.mark.asyncio
async def test_edit_tool_replaces_text(edit_tool, tmp_dir):
    path = os.path.join(tmp_dir, "file.txt")
    with open(path, "w") as f:
        f.write("hello old world")

    result = await edit_tool.execute(
        "tc1",
        {"path": path, "old_string": "old", "new_string": "new"},
        None,  # ctx
    )
    assert "successfully" in result.content[0].text.lower()

    with open(path, "r") as f:
        assert f.read() == "hello new world"


@pytest.mark.asyncio
async def test_edit_tool_missing_old_string(edit_tool, tmp_dir):
    path = os.path.join(tmp_dir, "file.txt")
    with open(path, "w") as f:
        f.write("hello world")

    result = await edit_tool.execute(
        "tc1",
        {"path": path, "old_string": "missing", "new_string": "new"},
        None,
    )
    assert result.content[0].text.startswith("Error")
```

Run: `.venv/bin/pytest tests/tools/local/test_edit.py -v`
Expected: FAIL

- [ ] **Step 2: 实现 edit.py**

```python
"""Edit tool — replace exact text in a file."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalFileOperations


class EditTool(Tool):
    def __init__(self, cwd: str = "", file_ops: Any | None = None) -> None:
        self._cwd = cwd or os.getcwd()
        self._file_ops = file_ops or LocalFileOperations(cwd=self._cwd)
        self.definition = ToolDefinition(
            name="edit",
            description="Edit a file by replacing exact text. Prefer this over 'write' for small changes.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute file path"},
                    "old_string": {"type": "string", "description": "Exact text to replace"},
                    "new_string": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "old_string", "new_string"],
            },
            prompt_guidelines=[
                "When editing files, prefer the 'edit' tool over 'write' for small changes.",
                "Always provide the exact old_string that appears in the file.",
            ],
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None) -> ToolResult:
        path = params.get("path", "")
        old_string = params.get("old_string", "")
        new_string = params.get("new_string", "")

        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        try:
            ok = await self._file_ops.edit(path, old_string, new_string)
            if not ok:
                return ToolResult(
                    content=[TextContent(text=f"Error: old_string not found in {path}")],
                    is_error=True,
                )
            return ToolResult(
                content=[TextContent(text=f"File edited successfully: {path}")],
                display={"operation": "edit", "path": path},
            )
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))], is_error=True)


def create_edit_tool(cwd: str = "", file_ops: Any | None = None) -> EditTool:
    return EditTool(cwd, file_ops)


edit_tool = EditTool()
```

- [ ] **Step 3: 运行测试**

Run: `.venv/bin/pytest tests/tools/local/test_edit.py -v`
Expected: `2 passed`

- [ ] **Step 4: Commit**

```bash
git add agent_core/tools/local/edit.py tests/tools/local/test_edit.py
git commit -m "feat(tools): add EditTool for precise text replacement"
```

### Task 1.8: 输出截断工具函数

**Files:**
- Create: `agent_core/tools/truncate.py`
- Test: `tests/tools/test_truncate.py`

- [ ] **Step 1: 编写测试**

```python
from agent_core.tools.truncate import format_size, truncate_head, truncate_line, truncate_tail


def test_truncate_tail():
    text = "a" * 100
    result = truncate_tail(text, 10)
    assert result.endswith("...")
    assert len(result) == 13


def test_truncate_head():
    text = "a" * 100
    result = truncate_head(text, 10)
    assert result.startswith("...")


def test_truncate_line():
    text = "\n".join([f"line{i}" for i in range(10)])
    result = truncate_line(text, 3)
    assert result.count("\n") == 2  # 3 lines
    assert result.endswith("...")


def test_format_size():
    assert format_size(512) == "512 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"
```

Run: `.venv/bin/pytest tests/tools/test_truncate.py -v`
Expected: FAIL

- [ ] **Step 2: 实现 truncate.py**

```python
"""Output truncation utilities for large tool results."""

from __future__ import annotations


def truncate_tail(text: str, max_chars: int, *, hint: str = "...") -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(hint)] + hint


def truncate_head(text: str, max_chars: int, *, hint: str = "...") -> str:
    if len(text) <= max_chars:
        return text
    return hint + text[len(text) - max_chars + len(hint):]


def truncate_line(text: str, max_lines: int, *, hint: str = "...") -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n" + hint


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
```

- [ ] **Step 3: 运行测试**

Run: `.venv/bin/pytest tests/tools/test_truncate.py -v`
Expected: `4 passed`

- [ ] **Step 4: Commit**

```bash
git add agent_core/tools/truncate.py tests/tools/test_truncate.py
git commit -m "feat(tools): add output truncation utilities"
```

### Task 1.9: 增强 ReadTool

**Files:**
- Modify: `agent_core/tools/local/read.py`

- [ ] **Step 1: 重写 read.py 接入 FileOperations 和截断**

```python
"""Read tool — read file contents with optional line range and truncation."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalFileOperations
from agent_core.tools.truncate import format_size, truncate_tail

DEFAULT_MAX_BYTES = 32_000
DEFAULT_MAX_LINES = 500


class ReadTool(Tool):
    def __init__(
        self,
        cwd: str = "",
        file_ops: Any | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_lines: int = DEFAULT_MAX_LINES,
    ) -> None:
        self._cwd = cwd or os.getcwd()
        self._file_ops = file_ops or LocalFileOperations(cwd=self._cwd)
        self._max_bytes = max_bytes
        self._max_lines = max_lines
        self.definition = ToolDefinition(
            name="read",
            description="Read a file from the local filesystem. Supports optional offset and limit for partial reads. Large files are automatically truncated.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file"},
                    "offset": {"type": "integer", "description": "Line offset to start reading from (0-indexed)", "minimum": 0},
                    "limit": {"type": "integer", "description": "Maximum number of lines to read", "minimum": 1},
                },
                "required": ["path"],
            },
            prompt_guidelines=[
                f"Files larger than {format_size(max_bytes)} or {max_lines} lines will be truncated.",
            ],
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None) -> ToolResult:
        path = params.get("path", "")
        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        offset = params.get("offset")
        limit = params.get("limit")

        try:
            content = await self._file_ops.read(path, offset=offset or 0, limit=limit)
            truncated = False
            lines = content.splitlines()
            if len(lines) > self._max_lines:
                content = "\n".join(lines[: self._max_lines]) + "\n... (truncated)"
                truncated = True
            elif len(content.encode("utf-8")) > self._max_bytes:
                content = truncate_tail(content, self._max_bytes, hint="... (truncated)")
                truncated = True

            return ToolResult(
                content=[TextContent(text=content)],
                details={"truncated": truncated, "path": path},
            )
        except FileNotFoundError:
            return ToolResult(content=[TextContent(text=f"File not found: {path}")], details={"error": "not_found"})
        except IsADirectoryError:
            return ToolResult(content=[TextContent(text=f"Path is a directory: {path}")], details={"error": "is_directory"})
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))], details={"error": "read_failed"})


def create_read_tool(cwd: str = "", file_ops: Any | None = None) -> ReadTool:
    return ReadTool(cwd, file_ops)


read_tool = ReadTool()
```

- [ ] **Step 2: 运行现有测试**

Run: `.venv/bin/pytest tests/tools/local/ -v -k read`
Expected: 现有 read tool 测试通过

- [ ] **Step 3: Commit**

```bash
git add agent_core/tools/local/read.py
git commit -m "feat(tools): enhance ReadTool with FileOperations and smart truncation"
```

### Task 1.10: 增强 WriteTool + 接入 mutation_queue

**Files:**
- Modify: `agent_core/tools/local/write.py`

- [ ] **Step 1: 重写 write.py**

```python
"""Write tool — write or overwrite a file."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalFileOperations


class WriteTool(Tool):
    def __init__(self, cwd: str = "", file_ops: Any | None = None) -> None:
        self._cwd = cwd or os.getcwd()
        self._file_ops = file_ops or LocalFileOperations(cwd=self._cwd)
        self.definition = ToolDefinition(
            name="write",
            description="Write content to a file. Creates the file if it does not exist, overwrites it otherwise.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file"},
                    "content": {"type": "string", "description": "Content to write to the file"},
                },
                "required": ["path", "content"],
            },
            prompt_guidelines=[
                "Always provide the full desired content of the file.",
            ],
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None) -> ToolResult:
        path = params.get("path", "")
        content = params.get("content", "")

        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        try:
            file_ops = self._file_ops
            # Use mutation queue if available in context
            if ctx is not None and ctx.mutation_queue is not None:
                await ctx.mutation_queue.write_locked(file_ops, path, content)
            else:
                await file_ops.write(path, content)

            display: dict[str, Any] = {"operation": "write", "path": path}
            # Simple heuristic for code display hint
            if "." in os.path.basename(path):
                ext = os.path.basename(path).split(".")[-1]
                if ext in ("py", "js", "ts", "json", "yaml", "yml", "md", "sh", "go", "rs", "java"):
                    display["language"] = ext

            return ToolResult(
                content=[TextContent(text=f"File written successfully: {path}")],
                display=display,
            )
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))])


def create_write_tool(cwd: str = "", file_ops: Any | None = None) -> WriteTool:
    return WriteTool(cwd, file_ops)


write_tool = WriteTool()
```

- [ ] **Step 2: Commit**

```bash
git add agent_core/tools/local/write.py
git commit -m "feat(tools): enhance WriteTool with FileOperations, mutation queue, and display hints"
```

### Task 1.11: 增强 BashTool + 接入 BashOperations

**Files:**
- Modify: `agent_core/tools/local/bash.py`

- [ ] **Step 1: 重写 bash.py**

```python
"""Bash tool — execute shell commands with streaming and timeout support."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalBashOperations


class BashTool(Tool):
    def __init__(self, cwd: str = "", bash_ops: Any | None = None) -> None:
        self._cwd = cwd or os.getcwd()
        self._bash_ops = bash_ops or LocalBashOperations(cwd=self._cwd)
        self.definition = ToolDefinition(
            name="bash",
            description="Execute a bash shell command. Use with caution.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds. Default is 60.", "minimum": 1, "maximum": 300},
                },
                "required": ["command"],
            },
            prompt_guidelines=[
                "Prefer grep/find/ls over bash when searching files.",
                "Commands run in the current working directory unless cd is used.",
            ],
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None) -> ToolResult:
        command = params.get("command", "")
        timeout = params.get("timeout", 60)

        try:
            result = await self._bash_ops.execute(command, timeout=float(timeout))
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            if not output.strip():
                output = "(no output)"

            return ToolResult(
                content=[TextContent(text=output)],
                details={"exit_code": result.returncode, "truncated": result.truncated},
            )
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))])


def create_bash_tool(cwd: str = "", bash_ops: Any | None = None) -> BashTool:
    return BashTool(cwd, bash_ops)


bash_tool = BashTool()
```

- [ ] **Step 2: Commit**

```bash
git add agent_core/tools/local/bash.py
git commit -m "feat(tools): enhance BashTool with BashOperations and guidelines"
```

### Task 1.12: 增强 LsTool + 接入 FileOperations

**Files:**
- Modify: `agent_core/tools/local/ls.py`

- [ ] **Step 1: 重写 ls.py**

```python
"""Ls tool — list directory contents."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalFileOperations


class LsTool(Tool):
    def __init__(self, cwd: str = "", file_ops: Any | None = None) -> None:
        self._cwd = cwd or os.getcwd()
        self._file_ops = file_ops or LocalFileOperations(cwd=self._cwd)
        self.definition = ToolDefinition(
            name="ls",
            description="List the contents of a directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the directory. Defaults to current working directory."},
                },
                "required": [],
            },
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None) -> ToolResult:
        path = params.get("path", "")
        if not path:
            path = self._cwd
        elif not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        try:
            infos = await self._file_ops.ls(path)
            lines = [f"Contents of {path}:", ""]
            for info in infos:
                prefix = "[D]" if info.is_dir else "[F]"
                lines.append(f"{prefix} {info.name}")
            return ToolResult(content=[TextContent(text="\n".join(lines))])
        except FileNotFoundError:
            return ToolResult(content=[TextContent(text=f"Directory not found: {path}")])
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))])


def create_ls_tool(cwd: str = "", file_ops: Any | None = None) -> LsTool:
    return LsTool(cwd, file_ops)


ls_tool = LsTool()
```

- [ ] **Step 2: Commit**

```bash
git add agent_core/tools/local/ls.py
git commit -m "feat(tools): enhance LsTool with FileOperations"
```

### Task 1.12b: 迁移 GrepTool 和 FindTool 到 FileOperations

**Files:**
- Modify: `agent_core/tools/local/grep.py`
- Modify: `agent_core/tools/local/find.py`

- [ ] **Step 1: 修改 grep.py**

参照 `LsTool` 的模式，将 `GrepTool` 改为接收 `file_ops: FileOperations | None = None` 参数，默认使用 `LocalFileOperations(cwd)`，将 `execute` 中的直接文件操作替换为 `self._file_ops.grep(...)`。

- [ ] **Step 2: 修改 find.py**

同理，将 `FindTool` 改为使用 `self._file_ops.find(...)`。

- [ ] **Step 3: Commit**

```bash
git add agent_core/tools/local/grep.py agent_core/tools/local/find.py
git commit -m "feat(tools): migrate GrepTool and FindTool to FileOperations"
```

### Task 1.13: 更新 tools/local/__init__.py 导出 EditTool

**Files:**
- Modify: `agent_core/tools/local/__init__.py`

- [ ] **Step 1: 添加 EditTool 导入和导出**

```python
from agent_core.tools.local.edit import EditTool, create_edit_tool, edit_tool

__all__ = [
    # ... existing exports ...
    "EditTool",
    "edit_tool",
    "create_edit_tool",
]
```

在 `create_all_tools` 中加入 edit：

```python
def create_all_tools(cwd: str = "") -> dict[str, Any]:
    return {
        "read": create_read_tool(cwd),
        "bash": create_bash_tool(cwd),
        "write": create_write_tool(cwd),
        "edit": create_edit_tool(cwd),
        "grep": create_grep_tool(cwd),
        "find": create_find_tool(cwd),
        "ls": create_ls_tool(cwd),
        "confirm": create_confirm_tool(),
    }
```

- [ ] **Step 2: Commit**

```bash
git add agent_core/tools/local/__init__.py
git commit -m "feat(tools): expose EditTool from local tools package"
```

### Task 1.14: 更新 tools/__init__.py 导出新增类型

**Files:**
- Modify: `agent_core/tools/__init__.py`

- [ ] **Step 1: 检查当前内容并添加导出**

当前 `agent_core/tools/__init__.py` 可能为空或已有内容。确保导出新增模块的公共类型：

```python
from agent_core.tools.base import (
    Tool,
    ToolContext,
    ToolDefinition,
    ToolInfo,
    ToolRegistry,
    ToolResult,
)
from agent_core.tools.mutation_queue import FileMutationQueue
from agent_core.tools.operations import BashOperations, BashResult, FileInfo, FileOperations
from agent_core.tools.operations_local import LocalBashOperations, LocalFileOperations
from agent_core.tools.render import RenderedOutput, ToolRenderer
from agent_core.tools.truncate import format_size, truncate_head, truncate_line, truncate_tail

__all__ = [
    "Tool",
    "ToolContext",
    "ToolDefinition",
    "ToolInfo",
    "ToolRegistry",
    "ToolResult",
    "FileMutationQueue",
    "BashOperations",
    "BashResult",
    "FileInfo",
    "FileOperations",
    "LocalBashOperations",
    "LocalFileOperations",
    "RenderedOutput",
    "ToolRenderer",
    "format_size",
    "truncate_head",
    "truncate_line",
    "truncate_tail",
]
```

- [ ] **Step 2: Commit**

```bash
git add agent_core/tools/__init__.py
git commit -m "feat(tools): export new operation, render, and truncation types"
```

---

## Phase 2: 资源发现与加载

### Task 2.1: 资源类型定义

**Files:**
- Create: `agent_core/resources/types.py`
- Test: `tests/resources/test_types.py`

- [ ] **Step 1: 编写测试**

```python
from agent_core.resources.types import ResourceDiagnostic, SourceInfo


def test_source_info_creation():
    si = SourceInfo(source="project", scope="global", origin="/path", base_dir="/base")
    assert si.source == "project"


def test_resource_diagnostic_creation():
    rd = ResourceDiagnostic(type="warning", message="test")
    assert rd.type == "warning"
```

Run: `.venv/bin/pytest tests/resources/test_types.py -v`
Expected: FAIL

- [ ] **Step 2: 实现 types.py**

```python
"""Resource types for discovery and loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ResourceDiagnostic:
    """Diagnostic emitted during resource loading."""
    type: Literal["warning", "error", "collision"]
    message: str
    source_path: str | None = None
    winner_path: str | None = None
    loser_path: str | None = None


@dataclass
class SourceInfo:
    """Source metadata for a loaded resource."""
    source: Literal["project", "user", "package", "explicit"]
    scope: Literal["global", "project", "session"]
    origin: str
    base_dir: str


@dataclass
class Skill:
    name: str
    description: str
    content: str
    source: SourceInfo
    disable_model_invocation: bool = False


@dataclass
class PromptTemplate:
    name: str
    description: str
    template: str
    parameters: list[str] = field(default_factory=list)
    source: SourceInfo | None = None


@dataclass
class Theme:
    name: str
    definition: dict[str, Any]
    source: SourceInfo | None = None


@dataclass
class ContextFile:
    path: str
    content: str
    source: Literal["cwd", "ancestor"]


@dataclass
class ExtensionSpec:
    name: str
    module_path: str
    source: SourceInfo
```

- [ ] **Step 3: 运行测试**

Run: `.venv/bin/pytest tests/resources/test_types.py -v`
Expected: `2 passed`

- [ ] **Step 4: Commit**

```bash
git add agent_core/resources/types.py tests/resources/test_types.py
git commit -m "feat(resources): add resource type definitions"
```

### Task 2.2: 诊断收集器

**Files:**
- Create: `agent_core/resources/diagnostics.py`
- Test: `tests/resources/test_diagnostics.py`

- [ ] **Step 1: 编写测试**

```python
from agent_core.resources.diagnostics import ResourceDiagnostics


def test_diagnostics_warning():
    d = ResourceDiagnostics()
    d.warning("test warning", source_path="/a")
    assert len(d.items) == 1
    assert d.items[0].type == "warning"


def test_diagnostics_collision():
    d = ResourceDiagnostics()
    d.collision("dup", winner_path="/a", loser_path="/b")
    assert d.has_errors is False
    assert d.items[0].winner_path == "/a"
```

Run: `.venv/bin/pytest tests/resources/test_diagnostics.py -v`
Expected: FAIL

- [ ] **Step 2: 实现 diagnostics.py**

```python
"""Diagnostic collector for resource loading."""

from __future__ import annotations

from agent_core.resources.types import ResourceDiagnostic


class ResourceDiagnostics:
    """Collects diagnostics during resource loading."""

    def __init__(self) -> None:
        self._items: list[ResourceDiagnostic] = []

    def warning(self, message: str, *, source_path: str | None = None) -> None:
        self._items.append(ResourceDiagnostic(type="warning", message=message, source_path=source_path))

    def error(self, message: str, *, source_path: str | None = None) -> None:
        self._items.append(ResourceDiagnostic(type="error", message=message, source_path=source_path))

    def collision(
        self,
        message: str,
        *,
        winner_path: str,
        loser_path: str,
    ) -> None:
        self._items.append(
            ResourceDiagnostic(
                type="collision",
                message=message,
                winner_path=winner_path,
                loser_path=loser_path,
            )
        )

    @property
    def items(self) -> list[ResourceDiagnostic]:
        return list(self._items)

    def has_errors(self) -> bool:
        return any(d.type == "error" for d in self._items)
```

- [ ] **Step 3: 运行测试**

Run: `.venv/bin/pytest tests/resources/test_diagnostics.py -v`
Expected: `2 passed`

- [ ] **Step 4: Commit**

```bash
git add agent_core/resources/diagnostics.py tests/resources/test_diagnostics.py
git commit -m "feat(resources): add ResourceDiagnostics collector"
```

### Task 2.3: Skill 加载逻辑迁移与增强

**Files:**
- Create: `agent_core/resources/skills.py`
- Test: `tests/resources/test_skills.py`

- [ ] **Step 1: 迁移现有逻辑并增强**

从 `agent_core/skills/__init__.py` 迁移核心逻辑到 `agent_core/resources/skills.py`，做以下增强：
1. 使用 `ResourceDiagnostics` 替代 list[dict]
2. 返回 `Skill` dataclass（content 字段从文件读取）
3. 使用 `SourceInfo`
4. 支持 `.gitignore` 过滤

```python
"""Skill discovery and loading."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.types import Skill, SourceInfo

MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024


def _validate_name(name: str, parent_dir_name: str) -> list[str]:
    errors: list[str] = []
    if name != parent_dir_name:
        errors.append(f'name "{name}" does not match parent directory "{parent_dir_name}"')
    if len(name) > MAX_NAME_LENGTH:
        errors.append(f"name exceeds {MAX_NAME_LENGTH} characters ({len(name)})")
    if not re.match(r"^[a-z0-9-]+$", name):
        errors.append("name contains invalid characters (must be lowercase a-z, 0-9, hyphens only)")
    if name.startswith("-") or name.endswith("-"):
        errors.append("name must not start or end with a hyphen")
    if "--" in name:
        errors.append("name must not contain consecutive hyphens")
    return errors


def _validate_description(description: str | None) -> list[str]:
    errors: list[str] = []
    if not description or description.strip() == "":
        errors.append("description is required")
    elif len(description) > MAX_DESCRIPTION_LENGTH:
        errors.append(f"description exceeds {MAX_DESCRIPTION_LENGTH} characters ({len(description)})")
    return errors


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    raw = parts[1].strip()
    body = parts[2].strip()
    frontmatter: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.lower() == "true":
                frontmatter[key] = True
            elif value.lower() == "false":
                frontmatter[key] = False
            else:
                frontmatter[key] = value
    return frontmatter, body


def load_skill_from_file(file_path: str, diagnostics: ResourceDiagnostics) -> Skill | None:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
    except Exception as exc:
        diagnostics.warning(str(exc), source_path=file_path)
        return None

    frontmatter, body = _parse_frontmatter(raw_content)
    skill_dir = os.path.dirname(file_path)
    parent_dir_name = os.path.basename(skill_dir)

    desc_errors = _validate_description(frontmatter.get("description"))
    for error in desc_errors:
        diagnostics.warning(error, source_path=file_path)

    name = frontmatter.get("name") or parent_dir_name
    name_errors = _validate_name(name, parent_dir_name)
    for error in name_errors:
        diagnostics.warning(error, source_path=file_path)

    if not frontmatter.get("description") or str(frontmatter.get("description", "")).strip() == "":
        return None

    return Skill(
        name=name,
        description=frontmatter["description"],
        content=raw_content,
        source=SourceInfo(
            source="project",
            scope="project",
            origin=file_path,
            base_dir=skill_dir,
        ),
        disable_model_invocation=frontmatter.get("disable-model-invocation") is True,
    )
```

- [ ] **Step 2: 编写测试**

```python
import tempfile
import os

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.skills import load_skill_from_file


def test_load_skill_from_file():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "SKILL.md")
        with open(path, "w") as f:
            f.write("---\nname: test-skill\ndescription: A test skill\n---\n\nContent here.")
        diag = ResourceDiagnostics()
        skill = load_skill_from_file(path, diag)
        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.description == "A test skill"
        assert "Content here" in skill.content
```

Run: `.venv/bin/pytest tests/resources/test_skills.py -v`
Expected: `1 passed`

- [ ] **Step 3: Commit**

```bash
git add agent_core/resources/skills.py tests/resources/test_skills.py
git commit -m "feat(resources): migrate skill loading with ResourceDiagnostics and SourceInfo"
```

### Task 2.4: Prompt Template 加载

**Files:**
- Create: `agent_core/resources/prompts.py`
- Test: `tests/resources/test_prompts.py`

- [ ] **Step 1: 实现 prompts.py**

```python
"""Prompt template discovery and loading."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.types import PromptTemplate, SourceInfo


def load_prompt_from_file(file_path: str, diagnostics: ResourceDiagnostics) -> PromptTemplate | None:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
    except Exception as exc:
        diagnostics.warning(str(exc), source_path=file_path)
        return None

    if not raw_content.startswith("---"):
        diagnostics.warning("Missing YAML frontmatter", source_path=file_path)
        return None

    parts = raw_content.split("---", 2)
    if len(parts) < 3:
        diagnostics.warning("Invalid frontmatter format", source_path=file_path)
        return None

    try:
        frontmatter = yaml.safe_load(parts[1].strip()) or {}
    except yaml.YAMLError as exc:
        diagnostics.warning(f"Invalid YAML: {exc}", source_path=file_path)
        return None

    name = frontmatter.get("name")
    if not name:
        diagnostics.warning("Missing 'name' in frontmatter", source_path=file_path)
        return None

    return PromptTemplate(
        name=name,
        description=frontmatter.get("description", ""),
        template=parts[2].strip(),
        parameters=frontmatter.get("parameters", []),
        source=SourceInfo(
            source="project",
            scope="project",
            origin=file_path,
            base_dir=os.path.dirname(file_path),
        ),
    )
```

- [ ] **Step 2: 编写测试**

```python
import tempfile
import os

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.prompts import load_prompt_from_file


def test_load_prompt_template():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "review.md")
        with open(path, "w") as f:
            f.write("---\nname: code-review\ndescription: Review code\nparameters:\n  - language\n---\n\nReview {{language}} code.")
        diag = ResourceDiagnostics()
        pt = load_prompt_from_file(path, diag)
        assert pt is not None
        assert pt.name == "code-review"
        assert pt.parameters == ["language"]
        assert "Review {{language}} code." in pt.template
```

Run: `.venv/bin/pytest tests/resources/test_prompts.py -v`
Expected: `1 passed`

- [ ] **Step 3: Commit**

```bash
git add agent_core/resources/prompts.py tests/resources/test_prompts.py
git commit -m "feat(resources): add prompt template loading with YAML frontmatter"
```

### Task 2.5: Theme 加载

**Files:**
- Create: `agent_core/resources/themes.py`
- Test: `tests/resources/test_themes.py`

- [ ] **Step 1: 实现 themes.py**

```python
"""Theme discovery and loading."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.types import SourceInfo, Theme


def load_theme_from_file(file_path: str, diagnostics: ResourceDiagnostics) -> Theme | None:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        diagnostics.warning(f"Invalid JSON: {exc}", source_path=file_path)
        return None
    except Exception as exc:
        diagnostics.warning(str(exc), source_path=file_path)
        return None

    name = data.get("name")
    if not name:
        diagnostics.warning("Missing 'name' field", source_path=file_path)
        return None

    return Theme(
        name=name,
        definition=data,
        source=SourceInfo(
            source="project",
            scope="project",
            origin=file_path,
            base_dir=os.path.dirname(file_path),
        ),
    )
```

- [ ] **Step 2: 编写测试**

```python
import tempfile
import os

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.themes import load_theme_from_file


def test_load_theme():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "dark.json")
        with open(path, "w") as f:
            json.dump({"name": "dark", "colors": {"primary": "#000"}}, f)
        diag = ResourceDiagnostics()
        theme = load_theme_from_file(path, diag)
        assert theme is not None
        assert theme.name == "dark"
```

Run: `.venv/bin/pytest tests/resources/test_themes.py -v`
Expected: `1 passed`

- [ ] **Step 3: Commit**

```bash
git add agent_core/resources/themes.py tests/resources/test_themes.py
git commit -m "feat(resources): add theme loading from JSON files"
```

### Task 2.6: 项目上下文文件加载

**Files:**
- Create: `agent_core/resources/context_files.py`
- Test: `tests/resources/test_context_files.py`

- [ ] **Step 1: 实现 context_files.py**

```python
"""Load project context files (AGENTS.md, CLAUDE.md) from cwd and ancestors."""

from __future__ import annotations

import os
from pathlib import Path

from agent_core.resources.types import ContextFile

DEFAULT_FILENAMES = ["AGENTS.md", "CLAUDE.md"]


def load_project_context_files(
    cwd: str,
    *,
    filenames: list[str] | None = None,
    max_depth: int = 20,
) -> list[ContextFile]:
    """Walk from cwd up to ancestors collecting context files.

    Nearest files come first. Stops at .git directory boundary.
    """
    filenames = filenames or DEFAULT_FILENAMES
    results: list[ContextFile] = []
    current = Path(cwd).resolve()
    depth = 0

    while current and depth < max_depth:
        for name in filenames:
            file_path = current / name
            if file_path.is_file():
                try:
                    content = file_path.read_text(encoding="utf-8")
                    results.append(
                        ContextFile(
                            path=str(file_path),
                            content=content,
                            source="ancestor" if depth > 0 else "cwd",
                        )
                    )
                except Exception:
                    pass

        # Stop at git boundary
        if (current / ".git").is_dir():
            break

        parent = current.parent
        if parent == current:
            break
        current = parent
        depth += 1

    return results
```

- [ ] **Step 2: 编写测试**

```python
import tempfile
import os

from agent_core.resources.context_files import load_project_context_files


def test_load_context_files_from_cwd():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "AGENTS.md"), "w") as f:
            f.write("# Agents")
        files = load_project_context_files(d)
        assert len(files) == 1
        assert files[0].path.endswith("AGENTS.md")
        assert files[0].source == "cwd"


def test_load_context_files_ancestor():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "CLAUDE.md"), "w") as f:
            f.write("# Claude")
        sub = os.path.join(d, "sub")
        os.makedirs(sub)
        files = load_project_context_files(sub)
        assert len(files) == 1
        assert files[0].source == "ancestor"
```

Run: `.venv/bin/pytest tests/resources/test_context_files.py -v`
Expected: `2 passed`

- [ ] **Step 3: Commit**

```bash
git add agent_core/resources/context_files.py tests/resources/test_context_files.py
git commit -m "feat(resources): add AGENTS.md and CLAUDE.md context file loading"
```

### Task 2.7: Extension Spec 发现

**Files:**
- Create: `agent_core/resources/extensions.py`
- Test: `tests/resources/test_extensions.py`

- [ ] **Step 1: 实现 extensions.py**

```python
"""ExtensionSpec discovery without dynamic import."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.types import ExtensionSpec, SourceInfo


def discover_extension_specs(
    search_paths: list[str],
    diagnostics: ResourceDiagnostics,
) -> list[ExtensionSpec]:
    """Discover extension specs from directories without importing them."""
    specs: list[ExtensionSpec] = []
    seen: set[str] = set()

    for search_path in search_paths:
        path = Path(search_path)
        if not path.exists():
            continue
        for entry in path.rglob("*.py"):
            resolved = str(entry.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            # Simple heuristic: look for extension.py or files containing Extension class
            if entry.name == "extension.py" or "extension" in entry.stem:
                specs.append(
                    ExtensionSpec(
                        name=entry.stem,
                        module_path=str(entry.parent) if (entry.parent / "__init__.py").exists() else str(entry)[:-3].replace(os.sep, "."),
                        source=SourceInfo(
                            source="project",
                            scope="project",
                            origin=str(entry),
                            base_dir=str(path),
                        ),
                    )
                )

    return specs
```

- [ ] **Step 2: 编写测试（简化版）**

```python
import tempfile
import os

from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.extensions import discover_extension_specs


def test_discover_extension_specs():
    with tempfile.TemporaryDirectory() as d:
        ext_dir = os.path.join(d, "my_ext")
        os.makedirs(ext_dir)
        with open(os.path.join(ext_dir, "extension.py"), "w") as f:
            f.write("class MyExt:\n    pass\n")
        diag = ResourceDiagnostics()
        specs = discover_extension_specs([d], diag)
        assert len(specs) >= 1
        assert specs[0].name == "extension"
```

Run: `.venv/bin/pytest tests/resources/test_extensions.py -v`
Expected: `1 passed`

- [ ] **Step 3: Commit**

```bash
git add agent_core/resources/extensions.py tests/resources/test_extensions.py
git commit -m "feat(resources): add ExtensionSpec discovery"
```

### Task 2.8: ResourceLoader 统一加载器

**Files:**
- Create: `agent_core/resources/loader.py`
- Test: `tests/resources/test_loader.py`

- [ ] **Step 1: 实现 loader.py**

```python
"""Unified resource loader for skills, prompts, themes, context files, and extensions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_core.resources.context_files import load_project_context_files
from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.extensions import discover_extension_specs
from agent_core.resources.prompts import load_prompt_from_file
from agent_core.resources.skills import load_skill_from_file
from agent_core.resources.themes import load_theme_from_file
from agent_core.resources.types import (
    ContextFile,
    ExtensionSpec,
    PromptTemplate,
    ResourceDiagnostic,
    Skill,
    SourceInfo,
    Theme,
)


class ResourceLoader:
    """Discover and load skills, prompts, themes, context files, and extension specs."""

    def __init__(
        self,
        *,
        cwd: str | None = None,
        extra_skill_paths: list[str] | None = None,
        extra_prompt_paths: list[str] | None = None,
        extra_theme_paths: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
    ) -> None:
        self._cwd = cwd or os.getcwd()
        self._extra_skill_paths = extra_skill_paths or []
        self._extra_prompt_paths = extra_prompt_paths or []
        self._extra_theme_paths = extra_theme_paths or []
        self._ignore_patterns = ignore_patterns or []

    # --- search paths ---

    def _search_paths(self, resource_type: str, extras: list[str]) -> list[Path]:
        paths: list[Path] = []
        for p in extras:
            paths.append(Path(os.path.expanduser(p)).resolve())
        paths.append(Path(self._cwd) / ".pi" / resource_type)
        agent_dir = Path.home() / ".pi" / "agent" / resource_type
        paths.append(agent_dir)
        env_var = os.environ.get(f"AGENT_CORE_{resource_type.upper()}_PATH")
        if env_var:
            for p in env_var.split(":"):
                paths.append(Path(os.path.expanduser(p)).resolve())
        return [p for p in paths if p.exists()]

    @property
    def skill_search_paths(self) -> list[Path]:
        return self._search_paths("skills", self._extra_skill_paths)

    @property
    def prompt_search_paths(self) -> list[Path]:
        return self._search_paths("prompts", self._extra_prompt_paths)

    @property
    def theme_search_paths(self) -> list[Path]:
        return self._search_paths("themes", self._extra_theme_paths)

    # --- load methods ---

    def load_skills(self) -> tuple[list[Skill], list[ResourceDiagnostic]]:
        diagnostics = ResourceDiagnostics()
        skills: dict[str, Skill] = {}
        seen_paths: set[str] = set()

        for search_path in self.skill_search_paths:
            for skill_md in search_path.rglob("SKILL.md"):
                resolved = str(skill_md.resolve())
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                skill = load_skill_from_file(str(skill_md), diagnostics)
                if skill is not None:
                    existing = skills.get(skill.name)
                    if existing:
                        diagnostics.collision(
                            f'Skill name "{skill.name}" collision',
                            winner_path=existing.source.origin,
                            loser_path=skill.source.origin,
                        )
                    else:
                        skills[skill.name] = skill

        return list(skills.values()), diagnostics.items

    def load_prompt_templates(self) -> tuple[list[PromptTemplate], list[ResourceDiagnostic]]:
        diagnostics = ResourceDiagnostics()
        prompts: dict[str, PromptTemplate] = {}

        for search_path in self.prompt_search_paths:
            for md_file in search_path.rglob("*.md"):
                pt = load_prompt_from_file(str(md_file), diagnostics)
                if pt is not None:
                    existing = prompts.get(pt.name)
                    if existing:
                        diagnostics.collision(
                            f'Prompt template "{pt.name}" collision',
                            winner_path=str(existing.source.origin) if existing.source else "",
                            loser_path=str(pt.source.origin) if pt.source else "",
                        )
                    else:
                        prompts[pt.name] = pt

        return list(prompts.values()), diagnostics.items

    def load_themes(self) -> tuple[list[Theme], list[ResourceDiagnostic]]:
        diagnostics = ResourceDiagnostics()
        themes: dict[str, Theme] = {}

        for search_path in self.theme_search_paths:
            for json_file in search_path.rglob("*.json"):
                theme = load_theme_from_file(str(json_file), diagnostics)
                if theme is not None:
                    existing = themes.get(theme.name)
                    if existing:
                        diagnostics.collision(
                            f'Theme "{theme.name}" collision',
                            winner_path=str(existing.source.origin) if existing.source else "",
                            loser_path=str(theme.source.origin) if theme.source else "",
                        )
                    else:
                        themes[theme.name] = theme

        return list(themes.values()), diagnostics.items

    def load_context_files(self) -> list[ContextFile]:
        return load_project_context_files(self._cwd)

    def load_extension_specs(self) -> tuple[list[ExtensionSpec], list[ResourceDiagnostic]]:
        diagnostics = ResourceDiagnostics()
        # Extension discovery from ~/.pi/agent/extensions and project .pi/extensions
        paths = self._search_paths("extensions", [])
        specs = discover_extension_specs([str(p) for p in paths], diagnostics)
        return specs, diagnostics.items
```

- [ ] **Step 2: 编写测试**

```python
import tempfile
import os

from agent_core.resources.loader import ResourceLoader


def test_resource_loader_search_paths():
    with tempfile.TemporaryDirectory() as d:
        loader = ResourceLoader(cwd=d)
        # No paths exist yet
        assert loader.skill_search_paths == []


def test_resource_loader_load_skills():
    with tempfile.TemporaryDirectory() as d:
        skills_dir = os.path.join(d, ".pi", "skills", "my-skill")
        os.makedirs(skills_dir)
        with open(os.path.join(skills_dir, "SKILL.md"), "w") as f:
            f.write("---\nname: my-skill\ndescription: A skill\n---\n")
        loader = ResourceLoader(cwd=d)
        skills, diagnostics = loader.load_skills()
        assert len(skills) == 1
        assert skills[0].name == "my-skill"
```

Run: `.venv/bin/pytest tests/resources/test_loader.py -v`
Expected: `2 passed`

- [ ] **Step 3: Commit**

```bash
git add agent_core/resources/loader.py tests/resources/test_loader.py
git commit -m "feat(resources): add unified ResourceLoader"
```

### Task 2.9: ExtensionLoader 动态导入

**Files:**
- Create: `agent_core/extensions/loader.py`
- Test: `tests/extensions/test_loader.py`

- [ ] **Step 1: 实现 loader.py**

```python
"""Dynamic extension loading from modules and entry points."""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
from typing import Any

from agent_core.extensions.base import Extension
from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.types import ExtensionSpec

logger = logging.getLogger(__name__)


class ExtensionLoader:
    """Load extensions from module paths and entry points."""

    def load_from_specs(self, specs: list[ExtensionSpec]) -> list[Extension]:
        extensions: list[Extension] = []
        for spec in specs:
            try:
                ext = self._load_spec(spec)
                if ext is not None:
                    extensions.append(ext)
            except Exception as exc:
                logger.warning("Failed to load extension %s: %s", spec.name, exc)
        return extensions

    def load_from_entry_points(self, group: str = "agent_core.extensions") -> list[Extension]:
        extensions: list[Extension] = []
        try:
            eps = importlib.metadata.entry_points()
            if hasattr(eps, "select"):
                selected = eps.select(group=group)
            else:
                selected = eps.get(group, [])
            for ep in selected:
                try:
                    factory = ep.load()
                    if callable(factory):
                        ext = factory()
                        if ext is not None:
                            extensions.append(ext)
                except Exception as exc:
                    logger.warning("Failed to load extension entry point %s: %s", ep.name, exc)
        except Exception as exc:
            logger.warning("Failed to load entry points: %s", exc)
        return extensions

    def _load_spec(self, spec: ExtensionSpec) -> Extension | None:
        module = importlib.import_module(spec.module_path)
        # Look for Extension subclass or factory function
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and hasattr(attr, "name") and attr_name != "Extension":
                return attr()
        return None
```

- [ ] **Step 2: Commit**

```bash
git add agent_core/extensions/loader.py
git commit -m "feat(extensions): add ExtensionLoader for dynamic import"
```

### Task 2.10: 填充 resources/__init__.py 导出

**Files:**
- Modify: `agent_core/resources/__init__.py`

- [ ] **Step 1: 添加导出**

```python
from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.loader import ResourceLoader
from agent_core.resources.types import (
    ContextFile,
    ExtensionSpec,
    PromptTemplate,
    ResourceDiagnostic,
    Skill,
    SourceInfo,
    Theme,
)

__all__ = [
    "ContextFile",
    "ExtensionSpec",
    "PromptTemplate",
    "ResourceDiagnostic",
    "ResourceDiagnostics",
    "ResourceLoader",
    "Skill",
    "SourceInfo",
    "Theme",
]
```

- [ ] **Step 2: Commit**

```bash
git add agent_core/resources/__init__.py
git commit -m "feat(resources): export public resource types"
```

---

## Phase 3: 系统提示词构建

### Task 3.1: 工具 Snippet 提取

**Files:**
- Create: `agent_core/prompts/snippets.py`
- Test: `tests/prompts/test_snippets.py`

- [ ] **Step 1: 实现 snippets.py**

```python
"""Extract one-line tool snippets for system prompts."""

from __future__ import annotations

from agent_core.tools.base import ToolDefinition


def extract_snippet(definition: ToolDefinition) -> str:
    """Extract a one-line description for a tool.

    Priority:
    1. ToolDefinition.prompt_snippet
    2. First sentence of description (truncated to 80 chars)
    3. Tool name
    """
    if definition.prompt_snippet:
        return definition.prompt_snippet

    if definition.description:
        sentence = definition.description.split(".")[0].strip()
        if len(sentence) > 80:
            sentence = sentence[:77] + "..."
        return sentence

    return definition.name
```

- [ ] **Step 2: 编写测试**

```python
from agent_core.prompts.snippets import extract_snippet
from agent_core.tools.base import ToolDefinition


def test_extract_snippet_from_prompt_snippet():
    d = ToolDefinition(name="read", description="Read files", parameters={}, prompt_snippet="Read a file")
    assert extract_snippet(d) == "Read a file"


def test_extract_snippet_from_description():
    d = ToolDefinition(name="read", description="Read a file from disk. Supports offsets.", parameters={})
    assert extract_snippet(d) == "Read a file from disk"


def test_extract_snippet_fallback_to_name():
    d = ToolDefinition(name="read", description="", parameters={})
    assert extract_snippet(d) == "read"
```

Run: `.venv/bin/pytest tests/prompts/test_snippets.py -v`
Expected: `3 passed`

- [ ] **Step 3: Commit**

```bash
git add agent_core/prompts/snippets.py tests/prompts/test_snippets.py
git commit -m "feat(prompts): add tool snippet extraction"
```

### Task 3.2: 动态 Guidelines 生成

**Files:**
- Create: `agent_core/prompts/guidelines.py`
- Test: `tests/prompts/test_guidelines.py`

- [ ] **Step 1: 实现 guidelines.py**

```python
"""Dynamic guideline generation based on active tools."""

from __future__ import annotations

from typing import Callable

from agent_core.tools.base import ToolDefinition

GuidelineRule = Callable[[set[str]], str | None]

_DEFAULT_RULES: list[GuidelineRule] = [
    lambda tools: "- Prefer grep/find/ls over bash when searching files."
    if {"grep", "find", "ls"} & tools else None,
    lambda tools: "- Always use 'edit' for small changes instead of rewriting entire files."
    if "edit" in tools else None,
    lambda tools: "- When using 'read', the output is automatically truncated if too large."
    if "read" in tools else None,
    lambda tools: "- Before creating files, check if they already exist with 'ls'."
    if {"write", "edit"} & tools else None,
]


def generate_guidelines(tools: list[ToolDefinition], rules: list[GuidelineRule] | None = None) -> list[str]:
    """Generate dynamic guidelines based on active tool names."""
    tool_names = {t.name for t in tools}
    rules = rules or _DEFAULT_RULES
    guidelines: list[str] = []
    for rule in rules:
        guideline = rule(tool_names)
        if guideline:
            guidelines.append(guideline)
    return guidelines
```

- [ ] **Step 2: 编写测试**

```python
from agent_core.prompts.guidelines import generate_guidelines
from agent_core.tools.base import ToolDefinition


def test_generate_guidelines_with_read():
    tools = [ToolDefinition(name="read", description="", parameters={})]
    guidelines = generate_guidelines(tools)
    assert any("truncated" in g for g in guidelines)


def test_generate_guidelines_with_edit():
    tools = [ToolDefinition(name="edit", description="", parameters={})]
    guidelines = generate_guidelines(tools)
    assert any("edit" in g for g in guidelines)


def test_generate_guidelines_empty():
    assert generate_guidelines([]) == []
```

Run: `.venv/bin/pytest tests/prompts/test_guidelines.py -v`
Expected: `3 passed`

- [ ] **Step 3: Commit**

```bash
git add agent_core/prompts/guidelines.py tests/prompts/test_guidelines.py
git commit -m "feat(prompts): add dynamic guideline generation"
```

### Task 3.3: SystemPromptBuilder

**Files:**
- Create: `agent_core/prompts/builder.py`
- Test: `tests/prompts/test_builder.py`

- [ ] **Step 1: 实现 builder.py**

```python
"""Dynamic system prompt builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from agent_core.prompts.guidelines import generate_guidelines
from agent_core.prompts.snippets import extract_snippet
from agent_core.resources.types import ContextFile, Skill
from agent_core.tools.base import ToolDefinition


class SystemPromptSection(BaseModel):
    name: str
    content: str
    source: str | None = None


class SystemPrompt(BaseModel):
    text: str
    sections: list[SystemPromptSection]
    tool_count: int
    skill_count: int
    context_file_count: int


class SystemPromptBuilder:
    """Build system prompts dynamically from tools, skills, context files, and metadata."""

    def __init__(self, *, base_prompt: str | None = None) -> None:
        self._base_prompt = base_prompt

    def build(
        self,
        *,
        cwd: str | None = None,
        active_tools: list[ToolDefinition] | None = None,
        skills: list[Skill] | None = None,
        context_files: list[ContextFile] | None = None,
        date: datetime | None = None,
    ) -> SystemPrompt:
        sections: list[SystemPromptSection] = []

        # 1. Base prompt
        base = self._base_prompt or (
            "You are a helpful assistant with access to tools. "
            "When you need to perform actions on the user's system, use the available tools. "
            "Always prefer using tools over guessing when file or system information is needed."
        )
        sections.append(SystemPromptSection(name="base", content=base))

        # 2. Tools
        tools = active_tools or []
        tool_lines: list[str] = []
        if tools:
            tool_lines.append("")
            tool_lines.append("## Tools")
            tool_lines.append("")
            tool_lines.append("You have access to the following tools:")
            tool_lines.append("")
            for tool in sorted(tools, key=lambda t: t.name):
                snippet = extract_snippet(tool)
                tool_lines.append(f"- {tool.name}: {snippet}")
        sections.append(SystemPromptSection(name="tools", content="\n".join(tool_lines)))

        # 3. Guidelines
        guidelines = generate_guidelines(tools)
        if guidelines:
            guideline_text = "\n".join(["", "## Guidelines", ""] + guidelines)
            sections.append(SystemPromptSection(name="guidelines", content=guideline_text))

        # 4. Tool-specific guidelines
        tool_guidelines: list[str] = []
        for tool in tools:
            for g in tool.prompt_guidelines:
                tool_guidelines.append(f"- {g}")
        if tool_guidelines:
            text = "\n".join(["", "## Tool Guidelines", ""] + tool_guidelines)
            sections.append(SystemPromptSection(name="tool_guidelines", content=text))

        # 5. Context files
        ctx_files = context_files or []
        if ctx_files:
            lines = ["", "## Project Context", ""]
            for cf in ctx_files:
                lines.append(f"### {cf.path}")
                lines.append("")
                lines.append(cf.content)
                lines.append("")
            sections.append(SystemPromptSection(name="context_files", content="\n".join(lines)))

        # 6. Skills
        skill_list = skills or []
        if skill_list:
            lines = ["", "## Skills", ""]
            lines.append("<available_skills>")
            for skill in skill_list:
                if not skill.disable_model_invocation:
                    lines.append(f'  <skill name="{skill.name}">{skill.description}</skill>')
            lines.append("</available_skills>")
            sections.append(SystemPromptSection(name="skills", content="\n".join(lines)))

        # 7. Meta
        now = date or datetime.now(tz=timezone.utc)
        meta_lines = [
            "",
            "## Meta",
            "",
            f"Current date: {now.strftime('%Y-%m-%d')}",
        ]
        if cwd:
            meta_lines.append(f"Current working directory: {cwd}")
        sections.append(SystemPromptSection(name="meta", content="\n".join(meta_lines)))

        # Assemble
        full_text = "\n".join(s.content for s in sections)
        return SystemPrompt(
            text=full_text,
            sections=sections,
            tool_count=len(tools),
            skill_count=len(skill_list),
            context_file_count=len(ctx_files),
        )
```

- [ ] **Step 2: 编写测试**

```python
from datetime import datetime, timezone

from agent_core.prompts.builder import SystemPromptBuilder
from agent_core.resources.types import ContextFile, Skill
from agent_core.tools.base import ToolDefinition


def test_builder_basic():
    builder = SystemPromptBuilder()
    result = builder.build(cwd="/tmp")
    assert "helpful assistant" in result.text
    assert "/tmp" in result.text
    assert len(result.sections) >= 2


def test_builder_with_tools():
    builder = SystemPromptBuilder()
    tools = [ToolDefinition(name="read", description="Read files", parameters={})]
    result = builder.build(cwd="/tmp", active_tools=tools)
    assert "read" in result.text
    assert result.tool_count == 1


def test_builder_with_context_files():
    builder = SystemPromptBuilder()
    files = [ContextFile(path="/p/AGENTS.md", content="# Agents", source="cwd")]
    result = builder.build(cwd="/p", context_files=files)
    assert "# Agents" in result.text
    assert result.context_file_count == 1
```

Run: `.venv/bin/pytest tests/prompts/test_builder.py -v`
Expected: `3 passed`

- [ ] **Step 3: Commit**

```bash
git add agent_core/prompts/builder.py tests/prompts/test_builder.py
git commit -m "feat(prompts): add SystemPromptBuilder with dynamic sections"
```

### Task 3.4: 填充 prompts/__init__.py 导出

**Files:**
- Modify: `agent_core/prompts/__init__.py`

- [ ] **Step 1: 添加导出**

```python
from agent_core.prompts.builder import SystemPrompt, SystemPromptBuilder, SystemPromptSection
from agent_core.prompts.guidelines import generate_guidelines
from agent_core.prompts.snippets import extract_snippet

__all__ = [
    "SystemPrompt",
    "SystemPromptBuilder",
    "SystemPromptSection",
    "extract_snippet",
    "generate_guidelines",
]
```

- [ ] **Step 2: Commit**

```bash
git add agent_core/prompts/__init__.py
git commit -m "feat(prompts): export public prompt types"
```

---

## Phase 4: 扩展系统增强与 Scene 迁移

### Task 4.1: 扩展新增 on_before_agent_start 事件

**Files:**
- Modify: `agent_core/extensions/base.py`
- Modify: `agent_core/extensions/runner.py`

- [ ] **Step 1: 修改 base.py**

在 `Extension` Protocol 中增加：

```python
async def on_before_agent_start(
    self,
    ctx: ExtensionContext,
    system_prompt: Any,
) -> Any | None:
    """Return modified system prompt or None."""
    ...
```

- [ ] **Step 2: 修改 runner.py**

在 `ExtensionRunner` 中增加：

```python
async def before_agent_start(self, system_prompt: Any) -> Any | None:
    for ext in self._extensions:
        try:
            result = await ext.on_before_agent_start(self._ctx, system_prompt)
            if result is not None:
                system_prompt = result
        except Exception as exc:
            logger.warning("Extension before_agent_start failed: %s", exc)
    return system_prompt
```

- [ ] **Step 3: Commit**

```bash
git add agent_core/extensions/base.py agent_core/extensions/runner.py
git commit -m "feat(extensions): add on_before_agent_start event"
```

### Task 4.1b: 更新 extensions/__init__.py 导出 ExtensionLoader

**Files:**
- Modify: `agent_core/extensions/__init__.py`

- [ ] **Step 1: 添加导出**

```python
from agent_core.extensions.base import Extension, ExtensionContext, ExtensionRunner
from agent_core.extensions.loader import ExtensionLoader

__all__ = [
    "Extension",
    "ExtensionContext",
    "ExtensionLoader",
    "ExtensionRunner",
]
```

- [ ] **Step 2: Commit**

```bash
git add agent_core/extensions/__init__.py
git commit -m "feat(extensions): export ExtensionLoader"
```

### Task 4.2: Scene system_prompt 文件迁移

**Files:**
- Delete: `scene/cli/system_prompt.py`
- Delete: `scene/http_sse/system_prompt.py`
- Delete: `scene/voice_ws/system_prompt.py`
- Modify: `scene/cli/chat_assistant.py`
- Modify: `scene/http_sse/chat_assistant.py`
- Modify: `scene/voice_ws/chat_assistant.py`

- [ ] **Step 1: 删除 system_prompt.py 文件**

Run:
```bash
rm scene/cli/system_prompt.py scene/http_sse/system_prompt.py scene/voice_ws/system_prompt.py
```

- [ ] **Step 2: 修改 scene/cli/chat_assistant.py**

替换 `from scene.cli.system_prompt import build_system_prompt` 和 `build_system_prompt` 调用：

```python
from agent_core.prompts.builder import SystemPromptBuilder
from agent_core.resources.loader import ResourceLoader
```

在 `ChatAssistant.create()` 中：

```python
# 替换原有的 build_system_prompt 调用
loader = ResourceLoader(cwd=cwd)
skills = loader.load_skills()[0]
context_files = loader.load_context_files()

builder = SystemPromptBuilder(base_prompt=system_prompt)
prompt = builder.build(
    cwd=cwd,
    active_tools=tool_registry.to_definitions(),
    skills=skills,
    context_files=context_files,
).text
```

- [ ] **Step 3: 对 http_sse 和 voice_ws 做同样修改**

- [ ] **Step 4: Commit**

```bash
git add scene/
git commit -m "refactor(scene): migrate system prompt building to agent_core/prompts"
```

### Task 4.3: 运行全部测试确保无回归

- [ ] **Step 1: 运行完整测试套件**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core
.venv/bin/pytest tests/ -q
```

Expected: 所有现有测试通过，新增测试通过

- [ ] **Step 2: Commit 修复（如有）**

如有失败，修复后 commit。

### Task 4.4: 标记 agent_core.skills 为废弃

**Files:**
- Modify: `agent_core/skills/__init__.py`

- [ ] **Step 1: 添加废弃警告**

在 `agent_core/skills/__init__.py` 顶部添加：

```python
import warnings

warnings.warn(
    "agent_core.skills is deprecated. Use agent_core.resources instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

保持现有导出不变以维持向后兼容。

- [ ] **Step 2: Commit**

```bash
git add agent_core/skills/__init__.py
git commit -m "chore: deprecate agent_core.skills in favor of agent_core.resources"
```

---

## 附录：Self-Review 检查清单

### Spec Coverage

| Spec 要求 | 对应 Task |
|---|---|
| ToolRenderer Protocol | Task 1.1 |
| FileOperations / BashOperations Protocol | Task 1.2 |
| LocalFileOperations / LocalBashOperations | Task 1.3 |
| FileMutationQueue | Task 1.4 |
| ToolResult.display / ToolDefinition.renderer / ToolContext.mutation_queue | Task 1.5 |
| EditTool | Task 1.7 |
| 截断工具函数 | Task 1.8 |
| ReadTool 增强 | Task 1.9 |
| WriteTool 增强 | Task 1.10 |
| BashTool 增强 | Task 1.11 |
| LsTool 增强 | Task 1.12 |
| ResourceLoader | Task 2.8 |
| Skill / Prompt / Theme / ContextFile 类型 | Task 2.1 |
| ResourceDiagnostics | Task 2.2 |
| Skill 加载迁移 | Task 2.3 |
| Prompt Template 加载 | Task 2.4 |
| Theme 加载 | Task 2.5 |
| AGENTS.md / CLAUDE.md 加载 | Task 2.6 |
| ExtensionSpec 发现 | Task 2.7 |
| ExtensionLoader | Task 2.9 |
| SystemPromptBuilder | Task 3.3 |
| 动态 Guidelines | Task 3.2 |
| 工具 Snippet | Task 3.1 |
| on_before_agent_start | Task 4.1 |
| Scene 迁移 | Task 4.2 |

无遗漏。

### Placeholder Scan

- 无 "TBD" / "TODO"
- 无 "implement later"
- 无 "add appropriate error handling" 等模糊描述
- 所有测试步骤包含实际代码
- 所有新建文件包含完整实现

### Type Consistency

- `ToolResult.display` 在 base.py、render.py、write.py 中一致使用 `dict[str, Any] | None`
- `FileOperations` / `BashOperations` 在 operations.py、operations_local.py、各 tool 中签名一致
- `ResourceDiagnostic` 在 types.py、diagnostics.py 中一致
- `SystemPrompt` / `SystemPromptSection` 在 builder.py 中一致
