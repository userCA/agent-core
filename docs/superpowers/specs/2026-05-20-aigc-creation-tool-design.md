# AIGC 创作工具设计文档

## 1. 背景与目标

将咪咕 AI-GC 创作接口 (`/user/h5/ai-gc/create/v1.0`) 抽象为 agent-core 框架的工具，支持多种创作场景（视频、图片等）。

**核心挑战：**
- 不同场景（`scene=nolo`、`scene=xmas` 等）共用同一套底层 API，但业务参数不同
- 部分参数需要用户交互确认（模板选择、图片上传等）
- 认证信息（cookie/token）由前端请求 header 带入，不暴露给 LLM
- 创作任务异步完成，需要轮询查询结果

## 2. 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                         前端层                               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐ │
│  │ 请求header   │    │ HITL卡片渲染 │    │ 登录/授权页面    │ │
│  │ (cookie等)   │    │ (表单/选择)  │    │                 │ │
│  └──────┬──────┘    └──────┬──────┘    └─────────────────┘ │
└─────────┼──────────────────┼────────────────────────────────┘
          │                  │
          ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                      Agent / Session                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐ │
│  │ Extension    │    │ HumanInput  │    │ ToolContext      │ │
│  │ (认证+审批)  │───▶│ Gate        │───▶│ .metadata       │ │
│  │              │    │ (暂停/恢复)  │    │ (业务参数+认证)  │ │
│  └─────────────┘    └─────────────┘    └─────────────────┘ │
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
    │      # ctx.metadata 已包含 AgentState.metadata 的内容
    │      # 优先级: ctx.metadata["aigc_auth"] > 构造函数默认值 > 环境变量
    │
    ├── 2. 参数校验与补全
    │      missing = _check_required_params(params)
    │      if missing and hitl_schema_builder:
    │          # 抛出 HITL，等待用户补充参数
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

**方案：统一用 Extension 管理（方案A）**

不在 `ChatAssistant` 层单独配置 `before_tool_call` hook，而是通过 **Extension + `AgentState.metadata`** 统一管理认证注入和审批。

### 4.1 AgentState 扩展

```python
# agent_core/core/state.py
class AgentState(BaseModel):
    ...
    metadata: dict[str, Any] = Field(default_factory=dict)  # 新增
```

`metadata` 作为请求级/会话级的共享状态，scene 层写入，Extension 和 Tool 读取。

### 4.2 ToolContext.metadata 与 AgentState.metadata 的同步

**问题：** `ToolContext.metadata` 和 `AgentState.metadata` 是两个独立的 dict，工具无法通过 `ctx.metadata` 读到 Extension 写入 `AgentState.metadata` 的认证信息。

**方案：** 在 `_run_single_tool` 创建 `ToolContext` 时，将 `AgentState.metadata` 合并进去。

```python
# tool_runner.py _run_single_tool

# 从 config 中获取 agent_state（需新增传递）
agent_state = getattr(config, "agent_state", None)
base_metadata = dict(agent_state.metadata) if agent_state else {}

ctx = ToolContext(
    signal=abort_event,
    mutation_queue=mutation_queue,
    on_update=on_update,
    metadata=base_metadata,  # 携带 AgentState.metadata 的内容
)
```

**传递链路：**

```
Agent._run() → AgentLoopConfig(agent_state=self.state)
    → tool_runner._run_single_tool() → ToolContext(metadata=dict(agent_state.metadata))
        → tool.execute(ctx=ctx) → ctx.metadata 包含 aigc_auth 等
```

需要在 `AgentLoopConfig` 中新增 `agent_state` 字段，在 `Agent._run()` 中传入。

### 4.3 Scene 层写入请求上下文

```python
# scene/http_sse/chat_assistant.py（或 middleware）
# 每个请求进来时，将请求 header 写入 AgentState.metadata
agent.state.metadata["request_headers"] = dict(request.headers)
```

### 4.4 Extension 统一管理

```python
# agent_core/extensions/aigc_guard.py

class AigcGuardExt:
    """统一管理 AIGC 工具的认证注入和审批。"""
    name = "aigc-guard"

    async def on_before_tool_call(self, ctx: ExtensionContext, tool_call: Any) -> dict[str, Any] | None:
        name = getattr(tool_call, "name", "")
        if not name.startswith("create_"):
            return None

        headers = ctx.agent.state.metadata.get("request_headers", {})

        # 1. 认证注入
        ctx.agent.state.metadata["aigc_auth"] = {
            "uid": headers.get("uid"),
            "deviceid": headers.get("deviceid"),
            "channel": headers.get("channel"),
            "pacmtoken": headers.get("pacmtoken"),
            # ... 其他认证字段
        }

        # 2. 审批检查（示例）
        if name in ("create_nolo_video",):
            approved = ctx.agent.state.metadata.get("aigc_approved_tools", set())
            if name not in approved:
                return {
                    "block": True,
                    "reason": f"工具 {name} 需要管理员审批，请确认后继续。"
                }

        return None
```

### 4.5 工具侧读取认证

```python
# AigcCreationTool._resolve_auth
def _resolve_auth(self, metadata: dict[str, Any]) -> dict[str, str]:
    """认证信息优先级：metadata[aigc_auth] > 环境变量 > 默认值"""
    auth = metadata.get("aigc_auth", {})
    return {
        "uid": auth.get("uid") or os.environ.get("MIGU_UID") or DEFAULT_UID,
        "deviceid": auth.get("deviceid") or os.environ.get("MIGU_DEVICE_ID") or DEFAULT_DEVICE_ID,
        "channel": auth.get("channel") or os.environ.get("MIGU_CHANNEL") or DEFAULT_CHANNEL,
        "pacmtoken": auth.get("pacmtoken") or os.environ.get("MIGU_PACM_TOKEN"),
        # ... 其他字段
    }
```

## 5. HITL 参数收集与重试机制

### 5.1 当前框架行为（需要改进）

```python
# tool_runner.py 当前实现
except RequiresHumanInput as exc:
    future = human_input_gate.require_input(tc.id)
    yield HumanInputRequired(...)
    values = await future
    # ❌ 问题：values 被直接包装成 ToolResult，工具不会重新执行
    result = ToolResult(content=[TextContent(text=str(values))])
```

### 5.2 改进方案：HITL 恢复后重试工具

**目标：** 用户输入的参数合并到原调用参数中，工具重新执行。

```python
# tool_runner.py sequential 模式改进
except RequiresHumanInput as exc:
    future = human_input_gate.require_input(tc.id)
    yield HumanInputRequired(tool_call_id=tc.id, prompt=exc.prompt, input_schema=exc.input_schema)
    values = await future

    # 将用户输入合并到参数（用户输入优先级更高）
    merged_args = {**tc.arguments, **values}

    # 重试工具：重新走 _run_single_tool 以保持 hook 一致性
    retry_result = await _run_single_tool(
        tool_call=_patched_tool_call(tc, merged_args),
        registry=registry,
        before=before,
        after=after,
        signal=signal,
        mutation_queue=mutation_queue,
        on_update=on_update,
    )
    _, result, is_error = retry_result
```

**关键决策：**
- 用户输入的 `values` 与原参数 `tc.arguments` 合并（用户输入优先级更高）
- HITL 重试时重新走 `_run_single_tool`，确保 Extension 的 `on_before_tool_call` / `on_after_tool_call` 以及 `before_tool_call` / `after_tool_call` hook 均正常执行
- 这意味着认证注入和审批检查在重试时仍会生效（但认证已写入 `AgentState.metadata`，审批已通过，不会重复阻断）
- 仅影响 **sequential** 执行模式（需要 HITL 的工具不应并行）
- parallel 模式保持原行为（不支持 HITL 重试）

**`_patched_tool_call` 辅助函数：**

```python
def _patched_tool_call(tc: Any, merged_args: dict[str, Any]) -> Any:
    """Create a copy of the tool call with merged arguments for HITL retry."""
    # ToolCallContent 是 Pydantic model，用 model_copy 覆盖 arguments
    if hasattr(tc, "model_copy"):
        return tc.model_copy(update={"arguments": merged_args})
    # Fallback: 直接修改（不推荐，但作为兜底）
    tc.arguments = merged_args
    return tc
```

### 5.3 HITL 卡片定义示例

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

## 9. 测试策略

### 9.1 FakeProvider 测试模式

使用 `FakeProvider` 模拟 LLM 行为，测试完整的事件流：

```python
@pytest.mark.asyncio
async def test_aigc_tool_with_hitl():
    """Test HITL flow: tool pauses for params, resumes after human input."""
    provider = FakeProvider()
    provider.queue_script([
        StreamToolCallStart(id="tc1", name="create_nolo_video"),
        StreamToolCallEnd(id="tc1", arguments={"style_note": "温柔"}),
        StreamMessageEnd(stop_reason="tool_calls"),
    ])

    tool = create_nolo_video_tool()
    registry = ToolRegistry()
    registry.register(tool)

    agent = Agent(provider=provider, tool_registry=registry, ...)

    events = []
    agent.subscribe(lambda evt: events.append(evt))

    await agent.prompt("生成一个视频")

    # 验证 HumanInputRequired 事件被发出
    hitl_events = [e for e in events if isinstance(e, HumanInputRequired)]
    assert len(hitl_events) == 1
    assert hitl_events[0].tool_call_id == "tc1"

    # 模拟用户补充参数
    await agent.provide_human_input("tc1", {
        "template_id": "426",
        "input_images": ["img123"],
    })

    # 验证工具重新执行并返回结果
    end_events = [e for e in events if isinstance(e, ToolExecutionEnd)]
    assert len(end_events) == 1
    assert not end_events[0].is_error
```

### 9.2 单元测试

- `_build_payload`：验证不同场景的请求体结构
- `_extract_task_id`：验证各种响应格式的解析
- `_poll_result`：使用 `respx` mock HTTP 接口，测试轮询逻辑
- `_resolve_auth`：验证认证信息优先级

## 10. 任务拆分

1. **框架增强：AgentState 加 metadata**
   - `agent_core/core/state.py`：新增 `metadata: dict[str, Any]` 字段

2. **框架增强：修复 Extension → Agent 连接**
   - `agent_core/session/session.py`：`start()` 中将 `ExtensionRunner` 注册到 `Agent`

3. **框架增强：AgentState.metadata → ToolContext.metadata 同步**
   - `agent_core/core/context.py`：`AgentLoopConfig` 新增 `agent_state` 字段
   - `agent_core/core/agent.py`：`_run()` 中传入 `agent_state=self.state`
   - `agent_core/core/tool_runner.py`：`_run_single_tool` 创建 `ToolContext` 时合并 `agent_state.metadata`

4. **框架增强：HITL 恢复后重试工具**
   - `agent_core/core/tool_runner.py`：sequential 模式下 HITL 恢复后重新走 `_run_single_tool`
   - 新增 `_patched_tool_call` 辅助函数

5. **核心工具：AigcCreationTool 类**
   - 新建 `agent_core/tools/aigc_creation.py`
   - 实现 execute、_build_payload、_poll_result、_resolve_auth 等

6. **场景工厂：nolo 视频工具**
   - 实现 `create_nolo_video_tool` 工厂函数
   - 定义 parameters schema 和 HITL 卡片定义

7. **集成测试**
   - 使用 FakeProvider 测试完整 HITL 流程
   - 使用 respx mock HTTP 测试 API 调用

8. **（可选）新增场景**
   - 按同样模式添加 `create_xmas_card_tool` 等
