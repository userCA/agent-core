# AIGC 创作工具设计文档

## 1. 背景与目标

将咪咕 AI-GC 创作接口 (`/user/h5/ai-gc/create/v1.0`) 抽象为 agent-core 框架的工具，支持多种创作场景（视频、图片等）。

**核心挑战：**
- 不同场景（`scene=nolo`、`scene=xmas` 等）共用同一套底层 API，但业务参数不同
- 部分参数需要用户交互确认（模板选择、图片上传等）
- 认证信息（cookie/token）由前端请求 header 带入，不暴露给 LLM
- 创作任务异步完成，需要轮询查询结果

**设计原则：** 最小化框架改动。业务工具的需求不驱动核心 loop 逻辑变更。

## 2. 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                         前端层                               │
│  ┌─────────────┐    ┌─────────────┐                        │
│  │ 请求header   │    │ HITL卡片渲染 │                        │
│  │ (cookie等)   │    │ (表单/选择)  │                        │
│  └──────┬──────┘    └──────┬──────┘                         │
└─────────┼──────────────────┼────────────────────────────────┘
          │                  │
          ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                      Agent / Session                         │
│  ┌─────────────┐    ┌─────────────┐                        │
│  │ Extension    │    │ HumanInput  │                        │
│  │ (认证+审批)  │───▶│ Gate        │                        │
│  └─────────────┘    └─────────────┘                        │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                   AigcCreationTool                           │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐ │
│  │ 参数校验     │───▶│ 缺参→HITL   │───▶│ 构建API请求     │ │
│  │             │    │ 完整→直接执行│    │                 │ │
│  └─────────────┘    └─────────────┘    └─────────────────┘ │
│                              │                               │
│                              ▼                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  HTTP: POST /ai-gc/create/v1.0  →  获取taskId           │ │
│  │  HTTP: 轮询查询接口  →  状态SUCCESS/FAILURE/超时          │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 3. AigcCreationTool 设计

### 3.1 核心类

```python
# agent_core/tools/aigc_creation.py

class AigcCreationTool:
    """Generic AIGC content creation tool for Migu AI."""

    def __init__(
        self,
        *,
        # --- ToolDefinition ---
        name: str,
        description: str,
        parameters: dict[str, Any],
        # --- API 固定参数 ---
        scene: str,
        content_type: str,  # "video" | "pic" | ...
        template_id: str | None = None,
        template_name: str | None = None,
        # --- 端点与认证 (默认配置) ---
        api_url: str = DEFAULT_CREATE_URL,
        query_url: str = DEFAULT_QUERY_URL,
        uid: str | None = None,
        device_id: str | None = None,
        channel: str = DEFAULT_CHANNEL,
        # --- 轮询配置 ---
        poll_interval: float = POLL_INTERVAL,
        poll_max_attempts: int = POLL_MAX_ATTEMPTS,
        # --- HITL 配置 ---
        hitl_schema_builder: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None
```

### 3.2 execute 流程

```
execute(tool_call_id, params, ctx)
    │
    ├── 1. 提取认证信息
    │      auth_headers = _resolve_auth(ctx.metadata)
    │      # 优先级: ctx.metadata["aigc_auth"] > 构造函数默认值 > 环境变量
    │
    ├── 2. 参数校验与补全
    │      missing = _check_required_params(params)
    │      if missing and hitl_schema_builder:
    │          raise RequiresHumanInput(
    │              prompt="请补充以下创作参数",
    │              input_schema=hitl_schema_builder(missing)
    │          )
    │
    ├── 3. 构建请求体
    │      payload = _build_payload(params, auth_headers)
    │
    ├── 4. 创建任务
    │      resp = POST api_url, headers=auth_headers, json=payload
    │      task_id = _extract_task_id(resp.json())
    │
    ├── 5. 轮询结果
    │      result = _poll_result(task_id, auth_headers, ctx)
    │
    └── 6. 返回 ToolResult
           content=[TextContent(text=result_text)]
```

### 3.3 认证信息解析

工具通过 `ctx.metadata["aigc_auth"]` 读取认证信息（Extension 注入，见 §4.3）。

```python
def _resolve_auth(self, metadata: dict[str, Any]) -> dict[str, str]:
    """认证信息优先级：metadata[aigc_auth] > 构造函数 > 环境变量 > 默认值"""
    auth = metadata.get("aigc_auth", {})
    return {
        "uid": auth.get("uid") or self._uid or os.environ.get("MIGU_UID") or DEFAULT_UID,
        "deviceid": auth.get("deviceid") or self._device_id or os.environ.get("MIGU_DEVICE_ID") or DEFAULT_DEVICE_ID,
        "channel": auth.get("channel") or self._channel or os.environ.get("MIGU_CHANNEL") or DEFAULT_CHANNEL,
        "pacmtoken": auth.get("pacmtoken") or os.environ.get("MIGU_PACM_TOKEN"),
        # ... 其他 header 字段
    }
```

## 4. 认证信息注入机制

**方案：Extension + `before_tool_call` inject_metadata（精简方案）**

通过 Extension 统一管理认证注入和审批，利用 `before_tool_call` 的 `inject_metadata` 机制将认证信息传入 `ToolContext.metadata`。

### 4.1 框架增强：`before_tool_call` 支持 `inject_metadata`

当前 `before_tool_call` 只支持 `{"block": True, "reason": "..."}` 返回值。扩展为同时支持 `inject_metadata`，将数据注入 `ToolContext.metadata`。

```python
# tool_runner.py _run_single_tool 改动（~5行）

if before is not None:
    try:
        hook_result = await before(
            {"tool_call": tool_call, "args": tool_call.arguments}
        )
        if hook_result and hook_result.get("block"):
            result = ToolResult(
                content=[TextContent(text=hook_result.get("reason", "Blocked."))]
            )
            return tool_call, result, True
        # ✅ 新增：支持 inject_metadata
        if hook_result and hook_result.get("inject_metadata"):
            _extra_metadata.update(hook_result["inject_metadata"])
    except Exception as exc:
        logger.debug("before_tool_call hook failed: %s", exc)

ctx = ToolContext(
    signal=abort_event,
    mutation_queue=mutation_queue,
    on_update=on_update,
    metadata=_extra_metadata,  # ✅ 携带注入的 metadata
)
```

**影响范围：** 仅 `tool_runner.py`，~5 行改动，向后兼容（现有 hook 返回值不受影响）。

### 4.2 Extension 统一管理

```python
# agent_core/extensions/aigc_guard.py

class AigcGuardExt:
    """统一管理 AIGC 工具的认证注入和审批。"""
    name = "aigc-guard"

    async def on_before_tool_call(self, ctx: ExtensionContext, tool_call: Any) -> dict[str, Any] | None:
        name = getattr(tool_call, "name", "")
        if not name.startswith("create_"):
            return None

        # 从 ExtensionContext 获取请求 headers
        # （需在 ExtensionContext 中携带，见 §4.4）
        request_headers = ctx.request_headers

        # 1. 认证注入 → 通过 inject_metadata 传入 ToolContext
        result: dict[str, Any] = {
            "inject_metadata": {
                "aigc_auth": {
                    "uid": request_headers.get("uid"),
                    "deviceid": request_headers.get("deviceid"),
                    "channel": request_headers.get("channel"),
                    "pacmtoken": request_headers.get("pacmtoken"),
                }
            }
        }

        # 2. 审批检查
        if name in NEED_APPROVAL_TOOLS:
            if not self._check_approval(ctx.session_id, name):
                return {"block": True, "reason": f"工具 {name} 需要管理员审批。"}

        return result
```

### 4.3 框架增强：修复 Extension → Agent 连接

当前 `AgentSession.start()` 创建了 `ExtensionRunner` 但未将其 hook 注册到 `Agent`，导致 Extension 的 `on_before_tool_call` / `on_after_tool_call` 永远不会触发。

```python
# agent_core/session/session.py start() 改动

if self._ext_runner is not None:
    ext_ctx = ExtensionContext(...)
    self._ext_runner = ExtensionRunner(self._extensions, ext_ctx)
    # ✅ 新增：将 ExtensionRunner 注册到 Agent
    self._agent._before_tool_call = self._ext_runner.before_tool_call
    self._agent._after_tool_call = self._ext_runner.after_tool_call
```

**影响范围：** 仅 `session.py`，~2 行改动。

### 4.4 ExtensionContext 携带请求 headers

当前 `ExtensionContext` 只有 `session_id` / `agent` / `store`，没有请求上下文。需要让 Extension 能访问到前端传入的请求 headers。

**方案：** 给 `ExtensionContext` 新增 `request_headers` 字段，由 scene 层在创建 `AgentSession` 时传入。

```python
# extensions/base.py
@dataclass
class ExtensionContext:
    session_id: str
    agent: Any
    store: Any | None = None
    request_headers: dict[str, str] = field(default_factory=dict)  # 新增
```

scene 层在创建 `AgentSession` 时：
```python
ext_ctx = ExtensionContext(
    session_id=session_id,
    agent=agent,
    store=store,
    request_headers=dict(request.headers),  # 从当前 HTTP 请求注入
)
```

**影响范围：** `extensions/base.py` 加 1 个字段，`session.py` 修改 `ExtensionContext` 构造。

## 5. HITL 参数收集（不改框架）

### 5.1 当前框架行为（保持不变）

```
1. 工具缺参 → raise RequiresHumanInput(prompt, input_schema)
2. 框架 yield HumanInputRequired 事件 → 前端渲染卡片
3. 用户填写表单 → provide_human_input(tool_call_id, values)
4. 框架将 values 包装为 ToolResult 返回给 LLM
5. LLM 看到 "用户输入: {template_id:426, images:[...]}"
6. LLM 自动再次调用工具，这次带完整参数
7. 工具正常执行
```

**多一个 LLM turn，但零框架改动。** 对于创作类任务（本身要等几十秒轮询），多 1-2 秒可忽略。

### 5.2 HITL 卡片定义示例

工具自由定义 `input_schema`，前端根据 `tool_name` + `input_schema` 渲染。

```python
# nolo 视频工具示例
hitl_schema_builder = lambda missing: {
    "type": "template_form",
    "title": "选择视频创作模板",
    "fields": [
        {
            "name": "template_id",
            "label": "模板",
            "type": "select",
            "required": True,
            "options": [
                {"value": "426", "label": "时光温柔", "preview_url": "..."},
                {"value": "427", "label": "夏日海边", "preview_url": "..."},
            ]
        },
        {
            "name": "input_images",
            "label": "上传照片",
            "type": "image_upload",
            "required": True,
            "max": 3,
            "accept": ["image/jpeg", "image/png"]
        },
        {
            "name": "style_note",
            "label": "风格备注（可选）",
            "type": "text",
            "required": False,
            "placeholder": "例如：温暖、柔和"
        }
    ]
}
```

## 6. 场景注册方式

### 6.1 工厂函数模式

每个场景一个工厂函数，共享同一个 `AigcCreationTool` 类。

```python
# agent_core/tools/aigc_creation.py

def create_nolo_video_tool(
    *,
    api_url: str | None = None,
    uid: str | None = None,
    device_id: str | None = None,
    channel: str | None = None,
) -> AigcCreationTool:
    """Create nolo scene video generation tool."""
    return AigcCreationTool(
        name="create_nolo_video",
        description="生成nolo场景视频。需要选择模板并上传照片。",
        scene="nolo",
        content_type="video",
        template_id="426",
        template_name="时光温柔",
        parameters={
            "type": "object",
            "properties": {
                "template_id": {
                    "type": "string",
                    "description": "视频模板ID（可选，默认426-时光温柔）",
                },
                "input_images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "输入照片URL或fileId列表（1-3张）",
                },
                "style_note": {
                    "type": "string",
                    "description": "风格备注（可选）",
                },
            },
        },
        hitl_schema_builder=_nolo_hitl_schema,
        api_url=api_url,
        uid=uid,
        device_id=device_id,
        channel=channel,
    )


def create_xmas_card_tool(...) -> AigcCreationTool:
    """Create Christmas card generation tool."""
    return AigcCreationTool(
        name="create_xmas_card",
        description="生成圣诞主题贺卡。",
        scene="xmas",
        content_type="pic",
        ...
    )
```

### 6.2 注册到 ToolRegistry

```python
from agent_core.tools.base import ToolRegistry
from agent_core.tools.aigc_creation import create_nolo_video_tool, create_xmas_card_tool

registry = ToolRegistry()
registry.register(create_nolo_video_tool())
registry.register(create_xmas_card_tool())
```

### 6.3 新增场景的成本

新增一个场景只需：
1. 写一个工厂函数（~15行）
2. 定义该场景的 `parameters` JSON Schema
3. （可选）定义 `hitl_schema_builder` 如果该场景需要 HITL
4. 注册到 registry

**无需修改 `AigcCreationTool` 核心类。**

## 7. API 调用详细设计

### 7.1 创建任务请求

```python
# POST /user/h5/ai-gc/create/v1.0
payload = {
    "scene": self._scene,
    "taskSessionId": _generate_session_id(),
    "aigcContentResultInput": {
        "contentType": self._content_type,
    },
    "ext": {
        "rcToken": auth_headers.get("rc_token", ""),
    },
    "inputContent": {
        "inputMeta": {
            "templateId": params.get("template_id") or self._template_id,
            "aiTemplateName": params.get("template_name") or self._template_name,
            "messageData": json.dumps({
                "templateId": params.get("template_id") or self._template_id,
                "scene": self._scene,
                # ... 其他固定字段
            }),
        },
        "aigcInputContentList": [
            {
                "contentType": "pic",
                "picType": "thirdParty",
                "picFileId": img_id,
                "contentMeta": {"rawFileId": img_id},
            }
            for img_id in params.get("input_images", [])
        ],
    },
}
```

### 7.2 轮询查询

与 `TextToMusicTool` 类似，使用独立的查询端点轮询任务状态。

```python
async def _poll_result(self, client, headers, task_id, ctx) -> str:
    for attempt in range(self._poll_max_attempts):
        if ctx.signal.is_set():
            return "任务已取消"

        resp = await client.get(self._query_url, headers=headers, params={"taskId": task_id})
        data = resp.json()
        status = _extract_status(data)

        if status in ("SUCCESS", "COMPLETED"):
            urls = _extract_result_urls(data)
            return f"创作完成！\n" + "\n".join(f"  {i+1}. {url}" for i, url in enumerate(urls))

        if status in ("FAILED", "ERROR"):
            return f"创作失败: {_extract_error(data)}"

        if ctx.on_update:
            ctx.on_update(ToolResult(content=[TextContent(
                text=f"创作中... 第{attempt+1}次查询，状态: {status}"
            )]))

        await asyncio.sleep(self._poll_interval)

    return f"轮询超时，任务ID: {task_id}"
```

## 8. 错误处理

| 错误场景 | 处理方式 |
|---------|---------|
| 认证信息缺失 | 工具正常执行，API 返回 401/403，捕获后返回友好提示 |
| 参数缺失且工具无 HITL | 返回错误提示，告知缺少哪些参数 |
| 参数缺失且工具有 HITL | 抛出 `RequiresHumanInput`，等待用户补充 |
| API 调用失败 | 返回 HTTP 状态码和错误信息 |
| 任务创建成功但无 taskId | 返回原始响应供排查 |
| 轮询超时 | 返回 taskId，告知用户稍后手动查询 |
| 任务执行失败 | 返回服务端错误信息 |
| 用户取消（signal） | 中断轮询，返回取消提示 |

## 9. 框架改动汇总

**总计改动 3 个文件，约 10 行核心改动：**

| 文件 | 改动 | 行数 |
|------|------|------|
| `session/session.py` | ExtensionRunner 注册到 Agent + ExtensionContext 携带 request_headers | ~4行 |
| `extensions/base.py` | ExtensionContext 加 `request_headers` 字段 | ~1行 |
| `core/tool_runner.py` | `before_tool_call` 支持 `inject_metadata` | ~5行 |

**不改的核心文件：** `state.py`、`context.py`、`agent.py`、`loop.py` — 零改动。

## 10. 任务拆分

1. **框架增强：修复 Extension → Agent 连接 + request_headers**
   - `agent_core/extensions/base.py`：`ExtensionContext` 加 `request_headers` 字段
   - `agent_core/session/session.py`：`start()` 中将 `ExtensionRunner` 注册到 `Agent`，构造 `ExtensionContext` 时传入 request_headers

2. **框架增强：`before_tool_call` 支持 `inject_metadata`**
   - `agent_core/core/tool_runner.py`：`_run_single_tool` 中处理 `inject_metadata`，写入 `ToolContext.metadata`

3. **核心工具：AigcCreationTool 类**
   - 新建 `agent_core/tools/aigc_creation.py`
   - 实现 execute、_build_payload、_poll_result、_resolve_auth 等

4. **场景工厂：nolo 视频工具**
   - 实现 `create_nolo_video_tool` 工厂函数
   - 定义 parameters schema 和 HITL 卡片定义

5. **集成测试**
   - 使用 FakeProvider 测试 HITL 流程（缺参 → 卡片 → LLM 再次调用）
   - 使用 respx mock HTTP 测试 API 调用

6. **（可选）新增场景**
   - 按同样模式添加 `create_xmas_card_tool` 等
