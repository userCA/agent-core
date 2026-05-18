# agent-core 优化设计文档 —— 工具系统、资源加载、系统提示词

> 日期: 2026-05-18
> 范围: 以 agent_core 库级别优化为主，scene/ 层仅做必要适配（移除已迁入库的 system_prompt 逻辑）
> 目标: 补齐与 demo/core（pi-mono）在这三个领域的差距，使框架同时支撑 CLI 与云服务场景

---

## 1. 背景与动机

当前 agent_core 已具备基础的 Agent 运行时、Provider 适配、工具执行和扩展协议，但与 demo/core（成熟 TypeScript harness）相比，以下三个领域存在明显差距：

| 领域 | 当前状态 | demo/core 状态 |
|---|---|---|
| 工具系统 | 直接操作 fs/subprocess，无渲染层，无文件编辑冲突保护 | Pluggable operations（本地/SSH/容器）、渲染协议、mutation queue、edit 工具 |
| 资源发现 | 仅 Skill 目录扫描 | Skills + Prompts + Themes + Context files + Extensions + Package sources |
| 系统提示词 | 静态字符串拼接 | 动态构建（guidelines、tool snippets、context files、date、append prompt） |

这些差距导致：
- 工具结果无法在不同前端（TUI / Web / Voice）差异化展示
- 项目上下文（AGENTS.md / CLAUDE.md）无法自动注入
- 系统提示词无法根据可用工具体动态调整

---

## 2. 工具系统可插拔性优化

### 2.1 当前问题

1. `ToolResult` 只有 `content: list[TextContent | ImageContent]`，前端只能拿到纯文本
2. 本地工具（read/write/bash/edit）直接调用 `open()` / `asyncio.subprocess_shell`，无法替换为远程实现
3. 并发编辑同一文件时无保护，可能产生 race condition
4. 缺少 `edit` 工具，智能体只能通过 read + write 间接编辑
5. 无输出截断/格式化工具，大文件容易撑爆上下文窗口

### 2.2 目标设计

#### 2.2.1 工具结果渲染协议

引入可选的渲染层，允许工具定义如何展示其结果，而不影响送向 LLM 的文本内容。

```python
from typing import Any, Protocol
from pydantic import BaseModel

class RenderedOutput(BaseModel):
    """工具结果的渲染输出，供前端消费。"""
    text: str                           # 纯文本表示（送 LLM）
    display: dict[str, Any] | None = None  # 结构化展示数据（送前端）
    mime_type: str = "text/plain"

class ToolRenderer(Protocol):
    """可选渲染协议。Tool 实现方可同时实现此协议。"""
    async def render_call(self, tool_call_id: str, name: str, arguments: dict[str, Any]) -> str:
        """渲染工具调用摘要（如 'read /path/to/file'）。"""
        ...

    async def render_result(
        self,
        tool_call_id: str,
        name: str,
        result: "ToolResult",
        is_error: bool,
    ) -> RenderedOutput:
        """渲染工具执行结果。"""
        ...
```

**改动点**：
- `ToolResult` 增加可选字段 `display: dict[str, Any] | None`，与 `RenderedOutput.display` 对齐
- `ToolDefinition` 增加可选字段 `renderer: ToolRenderer | None`
- `ToolRegistry` 的 `list()` 返回的 `ToolInfo` 包含 `has_renderer: bool`

**向后兼容**：渲染层完全可选；不实现 `ToolRenderer` 的工具保持现有行为。

#### 2.2.2 可插拔操作层（Pluggable Operations）

将文件系统/子进程操作抽象为协议，允许本地、SSH、容器等不同后端注入。

```python
from dataclasses import dataclass
from typing import Protocol

@dataclass
class FileInfo:
    name: str
    path: str
    is_dir: bool
    size: int

class FileOperations(Protocol):
    """文件操作抽象。"""
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
    """命令执行抽象。"""
    async def execute(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> BashResult: ...
```

**内置实现**：

```python
class LocalFileOperations:
    """默认本地文件操作实现。"""
    def __init__(self, cwd: str | None = None): ...

class LocalBashOperations:
    """默认本地 bash 执行实现。"""
    def __init__(self, cwd: str | None = None, shell: str | None = None): ...
```

**工具改造**：
- `ReadTool`、`WriteTool`、`EditTool`、`LsTool`、`GrepTool`、`FindTool` 接收 `file_ops: FileOperations` 参数
- `BashTool` 接收 `bash_ops: BashOperations` 参数
- 默认使用 `LocalFileOperations()` / `LocalBashOperations()`，保持现有行为

#### 2.2.3 文件变更队列

```python
import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator

class FileMutationQueue:
    """按路径串行化并发文件编辑操作。"""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def acquire(self, path: str) -> AsyncIterator[None]:
        """获取指定路径的编辑锁。"""
        lock = self._locks[path]
        async with lock:
            yield

    async def read_locked(self, file_ops: FileOperations, path: str) -> str:
        """在锁保护下读取文件。"""
        async with self.acquire(path):
            return await file_ops.read(path)

    async def write_locked(self, file_ops: FileOperations, path: str, content: str) -> None:
        """在锁保护下写入文件。"""
        async with self.acquire(path):
            await file_ops.write(path, content)

    async def edit_locked(
        self, file_ops: FileOperations, path: str, old_text: str, new_text: str
    ) -> bool:
        """在锁保护下编辑文件。"""
        async with self.acquire(path):
            return await file_ops.edit(path, old_text, new_text)
```

**集成点**：
- `ToolContext` 增加 `mutation_queue: FileMutationQueue | None` 字段
- 文件类工具在执行时优先使用 `ctx.mutation_queue`，回退到无锁直接执行

#### 2.2.4 新增 edit 工具 + 增强现有工具

**EditTool**：

```python
class EditTool:
    """精确文本替换编辑工具，支持模糊匹配。"""

    definition = ToolDefinition(
        name="edit",
        description="Edit a file by replacing exact text.",
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

    def __init__(self, file_ops: FileOperations | None = None) -> None: ...
```

**ReadTool 增强**：
- 增加智能截断：`truncate_head`（保留尾部）、`truncate_tail`（保留头部）、`truncate_line`（按行截断）
- 增加大小格式化：`format_size(1024) -> "1.0 KB"`
- 增加 `DEFAULT_MAX_BYTES = 32000` / `DEFAULT_MAX_LINES = 500`
- 截断时在结果中附加 `truncated: true` 标记

**BashTool 增强**：
- 流式输出支持（通过 `ToolContext.on_update` 回调推送 partial output）
- 进程树清理（`asyncio.create_subprocess_shell` + `killpg`）
- 临时文件溢出处理（stdout > 1MB 时写入临时文件）
- 超时控制

**WriteTool 增强**：
- 支持 `display` 输出语法高亮元数据（前端可据此渲染代码块）

#### 2.2.5 输出截断工具函数

```python
def truncate_head(text: str, max_chars: int, *, hint: str = "...") -> str:
    """保留尾部，截断头部。"""

def truncate_tail(text: str, max_chars: int, *, hint: str = "...") -> str:
    """保留头部，截断尾部。"""

def truncate_line(text: str, max_lines: int, *, hint: str = "...") -> str:
    """按行截断，保留前 N 行。"""

def format_size(size_bytes: int) -> str:
    """将字节数格式化为人类可读字符串（B/KB/MB/GB）。"""
```

### 2.3 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `agent_core/tools/render.py` | 新建 | `RenderedOutput`, `ToolRenderer` Protocol |
| `agent_core/tools/operations.py` | 新建 | `FileOperations`, `BashOperations` Protocol |
| `agent_core/tools/operations_local.py` | 新建 | `LocalFileOperations`, `LocalBashOperations` 实现 |
| `agent_core/tools/mutation_queue.py` | 新建 | `FileMutationQueue` |
| `agent_core/tools/local/edit.py` | 新建 | `EditTool` |
| `agent_core/tools/local/read.py` | 修改 | 接入 `FileOperations`，增加智能截断 |
| `agent_core/tools/local/write.py` | 修改 | 接入 `FileOperations`，增加 `mutation_queue` |
| `agent_core/tools/local/bash.py` | 修改 | 接入 `BashOperations`，增加流式/超时/清理 |
| `agent_core/tools/local/ls.py` | 修改 | 接入 `FileOperations` |
| `agent_core/tools/local/grep.py` | 修改 | 接入 `FileOperations` |
| `agent_core/tools/local/find.py` | 修改 | 接入 `FileOperations` |
| `agent_core/tools/base.py` | 修改 | `ToolResult` 增加 `display`，`ToolDefinition` 增加 `renderer` |
| `agent_core/tools/__init__.py` | 修改 | 导出新增类型 |
| `agent_core/core/tool_runner.py` | 修改 | 将 `ToolContext.mutation_queue` 传给工具 |

---

## 3. 资源发现与加载优化

### 3.1 当前问题

1. 只有 `skills/__init__.py` 做 Skill 扫描，无统一的资源加载层
2. 不支持 AGENTS.md / CLAUDE.md 项目上下文自动加载
3. 无 Prompt Template 发现
4. 无 Theme 发现
5. 无 Extension 加载机制（`extensions/__init__.py` 为空）
6. 无 `.gitignore` / `.ignore` 支持
7. SourceInfo 不完整，碰撞检测仅针对 skill 名称

### 3.2 目标设计

#### 3.2.1 统一资源加载器 `ResourceLoader`

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

@dataclass
class ResourceDiagnostic:
    """资源加载过程中的诊断信息。"""
    type: Literal["warning", "error", "collision"]
    message: str
    source_path: str | None = None
    winner_path: str | None = None
    loser_path: str | None = None

@dataclass
class SourceInfo:
    """资源来源信息。"""
    source: Literal["project", "user", "package", "explicit"]
    scope: Literal["global", "project", "session"]
    origin: str           # 原始路径或包名
    base_dir: str         # 基础目录

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

class ResourceLoader:
    """统一发现 Skills、Prompts、Themes、Context Files、Extensions。"""

    def __init__(
        self,
        *,
        cwd: str | None = None,
        extra_skill_paths: list[str] | None = None,
        extra_prompt_paths: list[str] | None = None,
        extra_theme_paths: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
    ) -> None:
        ...

    # --- 技能 ---
    def load_skills(self) -> tuple[list[Skill], list[ResourceDiagnostic]]: ...

    # --- Prompt 模板 ---
    def load_prompt_templates(self) -> tuple[list[PromptTemplate], list[ResourceDiagnostic]]: ...

    # --- 主题 ---
    def load_themes(self) -> tuple[list[Theme], list[ResourceDiagnostic]]: ...

    # --- 项目上下文文件 ---
    def load_context_files(self) -> list[ContextFile]: ...

    # --- 扩展规格（不执行 import，仅收集元数据） ---
    def load_extension_specs(self) -> tuple[list[ExtensionSpec], list[ResourceDiagnostic]]: ...

    # --- 搜索路径 ---
    @property
    def skill_search_paths(self) -> list[Path]: ...
    @property
    def prompt_search_paths(self) -> list[Path]: ...
    @property
    def theme_search_paths(self) -> list[Path]: ...
```

#### 3.2.2 搜索路径优先级

对于每种资源类型（skills / prompts / themes / extensions），搜索路径按以下优先级合并：

```
1. 显式路径（通过 extra_*_paths 传入）
2. <cwd>/.pi/{resources}/
3. ~/.pi/agent/{resources}/
4. 环境变量 AGENT_CORE_{RESOURCES}_PATH 指定的目录（冒号分隔）
```

其中 `{resources}` 为 `skills` / `prompts` / `themes` / `extensions`。

#### 3.2.3 Skill 加载（基于现有实现增强）

保留现有 `load_skills_from_dir()` 的核心逻辑，增强：
- 支持 `.gitignore` / `.ignore` 过滤（调用 `pathspec` 或简单 glob 匹配）
- 支持 symlink 去重（通过 `Path.resolve()` 比较真实路径）
- 返回 `SourceInfo` 而非简单的 `base_dir`
- 碰撞检测覆盖所有搜索路径，产出 `ResourceDiagnostic`

#### 3.2.4 项目上下文文件 `AGENTS.md` / `CLAUDE.md`

```python
def load_project_context_files(
    cwd: str,
    *,
    filenames: list[str] | None = None,
    max_depth: int = 20,
) -> list[ContextFile]:
    """从 cwd 向上遍历祖先目录，收集 AGENTS.md 和 CLAUDE.md。

    最近的文件排在最前面。遇到 .git 目录时停止向上遍历（视为项目边界）。
    """
    ...
```

默认加载的文件名：`["AGENTS.md", "CLAUDE.md"]`

#### 3.2.5 Prompt Template 加载

Prompt Template 文件格式（Markdown + YAML frontmatter）：

```markdown
---
name: code-review
description: Review code for bugs and style issues
parameters:
  - language
  - code
---

Review the following {{language}} code:

```{{language}}
{{code}}
```
```

加载逻辑：
1. 扫描搜索路径下的所有 `.md` 文件
2. 解析 YAML frontmatter（`name`, `description`, `parameters`）
3. 剩余内容为 `template`
4. 碰撞检测：同名模板在不同路径中后加载的覆盖先加载的，产出 warning diagnostic

#### 3.2.6 Theme 加载

Theme 文件格式（JSON）：

```json
{
  "name": "dark",
  "colors": {
    "primary": "#4f46e5",
    "background": "#0f0f0f"
  }
}
```

加载逻辑：扫描搜索路径下的所有 `.json` 文件，验证顶层有 `name` 字段。

#### 3.2.7 Extension 加载机制

Extension 加载分为两步：

**Step 1: 发现（`ResourceLoader` 职责）**

```python
@dataclass
class ExtensionSpec:
    name: str
    module_path: str
    source: SourceInfo
```

扫描搜索路径下的 Python 文件和目录，寻找：
- `extension.py` 或 `__init__.py` 中定义了 `Extension` 子类
- 入口点 `agent_core.extensions` 指向的模块

**Step 2: 加载（`ExtensionLoader` 职责）**

```python
class ExtensionLoader:
    def load(self, specs: list[ExtensionSpec]) -> tuple[list[Extension], list[ResourceDiagnostic]]: ...
```

通过 `importlib.import_module()` 动态导入并实例化扩展。

#### 3.2.8 诊断收集器

```python
class ResourceDiagnostics:
    """资源加载过程中的诊断收集器。"""

    def __init__(self) -> None: ...
    def warning(self, message: str, *, source_path: str | None = None) -> None: ...
    def error(self, message: str, *, source_path: str | None = None) -> None: ...
    def collision(
        self,
        message: str,
        *,
        winner_path: str,
        loser_path: str,
    ) -> None: ...
    @property
    def items(self) -> list[ResourceDiagnostic]: ...
    def has_errors(self) -> bool: ...
```

### 3.3 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `agent_core/resources/__init__.py` | 新建 | 包入口 |
| `agent_core/resources/loader.py` | 新建 | `ResourceLoader` |
| `agent_core/resources/types.py` | 新建 | `Skill`, `PromptTemplate`, `Theme`, `ContextFile`, `SourceInfo`, `ResourceDiagnostic` |
| `agent_core/resources/diagnostics.py` | 新建 | `ResourceDiagnostics` 收集器 |
| `agent_core/resources/skills.py` | 新建 | Skill 加载逻辑（从现有 `skills/__init__.py` 迁移增强） |
| `agent_core/resources/prompts.py` | 新建 | Prompt Template 加载 |
| `agent_core/resources/themes.py` | 新建 | Theme 加载 |
| `agent_core/resources/context_files.py` | 新建 | `AGENTS.md` / `CLAUDE.md` 加载 |
| `agent_core/resources/extensions.py` | 新建 | ExtensionSpec 发现 |
| `agent_core/skills/__init__.py` | 删除或迁移 | 逻辑迁入 `agent_core/resources/skills.py` |
| `agent_core/extensions/loader.py` | 新建 | `ExtensionLoader`（import 阶段） |

---

## 4. 系统提示词构建优化

### 4.1 当前问题

1. `build_system_prompt()` 是静态函数，Agent 创建时调用一次后不再更新
2. 仅列出工具名称，无 one-line snippet 和动态 guidelines
3. 无 `AGENTS.md` / `CLAUDE.md` 注入
4. 无日期注入
5. 无 `APPEND_SYSTEM.md` 支持
6. 扩展无法动态修改系统提示词

### 4.2 目标设计

#### 4.2.1 动态系统提示构建器

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel

class SystemPromptSection(BaseModel):
    """系统提示词的一个段落。"""
    name: str           # e.g. "base", "tools", "guidelines", "context_files", "skills", "meta"
    content: str
    source: str | None = None  # 来源路径（context file 时使用）

class SystemPrompt(BaseModel):
    """构建完成的系统提示词。"""
    text: str                           # 完整拼接后的 prompt
    sections: list[SystemPromptSection]  # 分段信息，便于调试/前端展示
    tool_count: int
    skill_count: int
    context_file_count: int

class SystemPromptBuilder:
    """动态构建系统提示词。"""

    def __init__(
        self,
        *,
        base_prompt: str | None = None,
        resource_loader: ResourceLoader | None = None,
    ) -> None:
        ...

    async def build(
        self,
        *,
        cwd: str | None = None,
        active_tools: list[ToolDefinition] | None = None,
        skills: list[Skill] | None = None,
        context_files: list[ContextFile] | None = None,
        date: datetime | None = None,
        append_prompt_path: str | None = None,
    ) -> SystemPrompt:
        """构建系统提示词。"""
        ...
```

#### 4.2.2 构建段落顺序

构建出的 `SystemPrompt.text` 按以下顺序拼接：

```
1. Base system prompt（用户传入的 base_prompt）

2. Available tools
   ## Tools
   
   You have access to the following tools:
   
   - read: Read file contents
   - write: Write content to a file
   - edit: Replace text in a file
   ...
   
   (含每个工具的 name + one-line description)

3. Tool guidelines（根据可用工具动态生成）
   ## Guidelines
   
   - Prefer grep/find/ls over bash when searching files.
   - Always use 'edit' for small changes instead of rewriting entire files.
   - When using 'read', the output is automatically truncated if too large.
   ...

4. Tool-specific prompt_guidelines（各 ToolDefinition.prompt_guidelines）

5. Project context files
   ## Project Context
   
   ### AGENTS.md (from /path/to/project)
   <content>
   
   ### CLAUDE.md (from /path/to/project)
   <content>

6. Skills
   ## Skills
   
   <available_skills>
     <skill name="...">...</skill>
   </available_skills>

7. Meta information
   Current date: 2026-05-18
   Current working directory: /path/to/cwd

8. Append system prompt（从 .pi/APPEND_SYSTEM.md 或项目根目录加载）
```

#### 4.2.3 动态 Guidelines 生成

Guidelines 不是硬编码字符串，而是基于活跃工具集合动态生成：

```python
_guidelines_rules: list[Callable[[set[str]], str | None]] = [
    lambda tools: "- Prefer grep/find/ls over bash when searching files."
    if {"grep", "find", "ls"} & tools else None,
    lambda tools: "- Always use 'edit' for small changes instead of rewriting entire files."
    if "edit" in tools else None,
    lambda tools: "- When using 'read', the output is automatically truncated if too large."
    if "read" in tools else None,
    lambda tools: "- Before creating files, check if they already exist with 'ls'."
    if {"write", "edit"} & tools else None,
]
```

#### 4.2.4 工具 Snippet 生成

每个工具的 one-line description 来源优先级：
1. `ToolDefinition.prompt_snippet`
2. `ToolDefinition.description` 的首句（截断到 80 字符）
3. 工具名本身

#### 4.2.5 与扩展集成

扩展可通过 `before_agent_start` 事件修改系统提示词：

```python
class Extension(Protocol):
    # ... 现有事件 ...

    async def on_before_agent_start(
        self,
        ctx: ExtensionContext,
        system_prompt: SystemPrompt,
    ) -> SystemPrompt | None:
        """返回修改后的 SystemPrompt，或 None 表示不做修改。"""
        ...
```

`AgentSession.prompt()` 内部流程：
1. 调用 `SystemPromptBuilder.build()` 生成基础 prompt
2. 遍历扩展的 `on_before_agent_start`，允许修改
3. 将最终 `text` 赋值给 `AgentState.system_prompt`

#### 4.2.6 按需构建（非每次 prompt 重建）

为减少重复构建开销，`AgentSession` 层负责缓存和变化检测：
- `AgentSession` 记录上次构建时的 `active_tools`、`skills`、`context_files` 哈希/指纹
- `SystemPromptBuilder.build()` 本身无状态，每次调用都重新构建
- `AgentSession.prompt()` 仅在输入参数变化时调用 `build()`，否则复用缓存的 `SystemPrompt`
- 工具调用过程中不重建（工具调用不改变 system prompt）

### 4.3 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `agent_core/prompts/builder.py` | 新建 | `SystemPromptBuilder`, `SystemPrompt`, `SystemPromptSection` |
| `agent_core/prompts/guidelines.py` | 新建 | 动态 Guidelines 生成规则 |
| `agent_core/prompts/snippets.py` | 新建 | 工具 snippet 提取 |
| `agent_core/prompts/__init__.py` | 新建 | 包入口 |
| `agent_core/extensions/base.py` | 修改 | 增加 `on_before_agent_start` 事件 |
| `agent_core/session/session.py` | 修改 | `AgentSession` 集成 `SystemPromptBuilder` |
| `scene/cli/system_prompt.py` | 删除 | 逻辑迁入 `agent_core/prompts/` |
| `scene/http_sse/system_prompt.py` | 删除 | 逻辑迁入 `agent_core/prompts/` |
| `scene/voice_ws/system_prompt.py` | 删除 | 逻辑迁入 `agent_core/prompts/` |
| `scene/cli/chat_assistant.py` | 修改 | 使用 `SystemPromptBuilder` 替代本地 `build_system_prompt()` |
| `scene/http_sse/chat_assistant.py` | 修改 | 使用 `SystemPromptBuilder` |
| `scene/voice_ws/chat_assistant.py` | 修改 | 使用 `SystemPromptBuilder` |

---

## 5. 扩展系统增强（配合上述三方向）

### 5.1 当前问题

- `extensions/__init__.py` 为空，无加载机制
- 扩展无法注册工具、命令、flag
- 扩展无 `before_agent_start` 事件（系统提示词修改需求）
- 扩展无 `resources_discover` 事件

### 5.2 目标设计

#### 5.2.1 扩展加载

```python
# agent_core/extensions/loader.py
class ExtensionLoader:
    def load_from_specs(self, specs: list[ExtensionSpec]) -> list[Extension]: ...
    def load_from_modules(self, modules: list[str]) -> list[Extension]: ...
    def load_from_entry_points(self, group: str = "agent_core.extensions") -> list[Extension]: ...
```

#### 5.2.2 扩展注册能力

```python
class ExtensionContext:
    # ... 现有能力 ...

    def register_tool(self, tool: Tool) -> None: ...
    def get_active_tools(self) -> list[ToolDefinition]: ...
    def set_active_tools(self, names: list[str]) -> None: ...
```

#### 5.2.3 新增扩展事件

| 事件 | 触发时机 | 用途 |
|---|---|---|
| `on_before_agent_start` | `AgentSession.prompt()` 开始时 | 修改 system prompt、注入初始消息 |
| `on_resources_discover` | `ResourceLoader` 初始化时 | 扩展提供额外的 skill/prompt/theme 搜索路径 |

### 5.3 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `agent_core/extensions/loader.py` | 新建 | `ExtensionLoader` |
| `agent_core/extensions/base.py` | 修改 | 增加 `on_before_agent_start` |
| `agent_core/extensions/runner.py` | 修改 | 支持 `on_before_agent_start` 链式调用 |
| `agent_core/extensions/__init__.py` | 修改 | 导出 `ExtensionLoader` |

---

## 6. API 兼容性

### 6.1 向后兼容

所有改动遵循以下原则：
- 新增字段/参数均有默认值，不影响现有调用方
- `ToolRenderer`、`FileOperations`、`BashOperations` 均为可选注入
- `ResourceLoader` 是新增模块，不修改现有 `skills/__init__.py` 的导出（先 deprecate，再移除）
- `SystemPromptBuilder` 是新增模块，scene/ 层可逐步迁移

### 6.2 废弃计划

| 废弃项 | 替代 | 时间 |
|---|---|---|
| `agent_core.skills` 模块 | `agent_core.resources` | v1.1 标记 deprecated，v2 移除 |
| `scene/*/system_prompt.py` | `agent_core.prompts.SystemPromptBuilder` | 随本优化文档直接替换 |

---

## 7. 依赖变更

| 包 | 用途 | 安装方式 |
|---|---|---|
| `pathspec` >= 0.12 | `.gitignore` / `.ignore` 模式匹配 | 新增核心依赖 |
| `pyyaml` >= 6.0 | YAML frontmatter 解析 | 新增核心依赖（或替换为 `ruamel.yaml`） |

`pathspec` 和 `pyyaml` 均为常见依赖，体积可控。

---

## 8. 验证标准

1. **工具系统**
   - `EditTool` 可用，能精确替换文件内容
   - `FileMutationQueue` 能串行化同一文件的并发编辑
   - `LocalFileOperations` / `LocalBashOperations` 为默认实现，现有行为不变
   - `ToolResult.display` 能被扩展读取并透传给前端

2. **资源加载**
   - `ResourceLoader` 能从 `~/.pi/agent/skills/` 和 `<cwd>/.pi/skills/` 加载 skill（与现有行为一致）
   - `load_context_files()` 能从 cwd 向上遍历并收集 `AGENTS.md` / `CLAUDE.md`
   - 同名 skill 在不同路径中时产出 `ResourceDiagnostic(type="collision")`
   - `.gitignore` 被尊重

3. **系统提示词**
   - `SystemPromptBuilder.build()` 产出的 prompt 包含 tools、guidelines、context files、skills、date
   - Guidelines 随 active_tools 变化而动态变化
   - 扩展的 `on_before_agent_start` 能修改最终 prompt
   - scene/cli 的 system prompt 构建行为与现有版本等价

4. **回归测试**
   - 所有现有测试通过
   - `pytest tests/` 无新增警告

---

## 9. 与 demo/core 的对应关系

| demo/core (TS) | agent_core (Python) — 优化后 |
|---|---|
| `demo/core/tools/` 含 edit / render / mutation queue | `agent_core/tools/local/edit.py`, `mutation_queue.py`, `render.py` |
| `demo/core/tools/operations.ts` | `agent_core/tools/operations.py`, `operations_local.py` |
| `demo/core/resource-loader.ts` | `agent_core/resources/loader.py` |
| `demo/core/system-prompt.ts` | `agent_core/prompts/builder.py` |
| `demo/core/extensions/loader.ts` | `agent_core/extensions/loader.py` |
| `demo/core/extensions/types.ts` 中的 `before_agent_start` | `agent_core/extensions/base.py` 新增事件 |
