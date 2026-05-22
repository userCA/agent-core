# show_widget 工具设计

**日期:** 2026-05-22
**状态:** 已确认

## 概述

在 `agent_core/tools/widgets/` 下新增 `show_widget` 独立工具。该工具接收 LLM 生成的 HTML 片段,通过 `ToolResult.display` 返回结构化渲染元数据,由 `scene/http_sse` 前端在 iframe(`sandbox="allow-scripts"`,opaque origin)+ 严格 CSP 中渲染。首版为纯展示,`sendPrompt` 交互仅预留 postMessage 协议入口,未激活。

不修改任何现有能力。

## 架构

```
agent_core/tools/widgets/
├── __init__.py          # 导出 ShowWidgetTool
├── spec.py              # WIDGET_SPEC 常量(注入 description)
└── tool.py              # ShowWidgetTool 实现

scene/http_sse/events.py                  # ~4 行: widget display 透传
scene/http_sse/static/index.html           # ~60 行: renderWidget + handleWidgetMessage
```

## 数据流

```
LLM 调用 show_widget(html=..., title=..., height=...)
  → ShowWidgetTool.execute()
    → 校验 HTML(拒绝 <html>/<head>/<body>/<!DOCTYPE>, 大小限制 50KB)
    → 返回 ToolResult(
        content=[TextContent(text="[widget rendered: {title}]")],
        display={"widget": {"version": 1, "html": ..., "title": ..., "height": ...}}
      )
  → SSE: tool_end 事件携带 "display.widget" 键
  → 前端检测到 display.widget → 创建 iframe srcdoc → 渲染
```

- `content[0].text` 是供 LLM 上下文使用的占位符(不污染 HTML)。
- `display["widget"]` 仅前端消费,不进入 LLM 上下文。

## 工具 API

```python
ShowWidgetTool(
    name="show_widget",
    description=<WIDGET_SPEC 全文>,
    parameters={
        "type": "object",
        "properties": {
            "html": {
                "type": "string",
                "description": "完整 HTML 片段,需遵守设计规范"
            },
            "title": {
                "type": "string",
                "description": "可选展示标题"
            },
            "height": {
                "type": "integer",
                "description": "可选 iframe 高度(px),默认 400,最大 1200"
            }
        },
        "required": ["html"]
    }
)
```

**为什么把 WIDGET_SPEC 放在 `description`**:
- LLM provider(OpenAI / Anthropic)把工具列表的 `description` 作为 system message 的一部分**一次性发送**,后续 tool_call 不会重复发送 — 不存在"每次工具调用污染上下文"
- `prompt_snippet` 是单行简介格式(`SystemPromptBuilder` 拼成 `- {name}: {snippet}` 列表项),无法容纳多段 markdown 规范
- `description` 是工具规范的天然归属,LLM 调用工具时直接看到完整契约

### 返回结构

```python
# height 容错:非 int 或 ≤0 → 400;再 clamp 到 1200
h = params.get("height")
height = h if isinstance(h, int) and h > 0 else 400
height = min(height, 1200)

ToolResult(
    content=[TextContent(text=f"[widget rendered: {title or '未命名'}]")],
    display={
        "widget": {
            "version": 1,
            "html": <校验后的 html>,
            "title": title,
            "height": height,
        }
    }
)
```

### 校验(后端轻量)

| 检查项 | 行为 |
|---|---|
| HTML 大小 > 50KB | `raise ValueError("html size exceeds 50KB limit (got {n} bytes)")` |
| 包含 `<html>` / `<head>` / `<body>` / `<!DOCTYPE>` | `raise ValueError("html contains forbidden tag <{tag}>; 请删除后重新调用 show_widget")` |
| `height` 非 int 或 ≤0 | silent fallback 到 400(不 raise:容错优先,LLM 可能传 `"400"` / `0` / `None`) |
| 正常输入 | 正常返回,`display` 含 widget 元数据 |

**注意 1**: 不做 HTML 深度清洗。安全由 iframe sandbox + CSP 兜底,不重复造轮子。

**注意 2**: 校验失败时**直接 `raise ValueError`**(带明确的修复指令文案)。loop 捕获异常后会生成 `is_error=True` 的 `ToolExecutionEnd`,其 `result` 是 `ToolResult(content=[TextContent(text=str(exc))], display=None)`。`events.py` 的 `evt.result.display and 'widget' in evt.result.display` 守卫会因 `display` 为 `None` 而短路,前端不会渲染 widget,只显示普通 tool-error step(异常文本进入 `data.result`,由现有 `tool_end` 分支正常处理)。`ToolResult` 没有 `is_error` 字段(那是事件层属性),因此我们用 raise 而非返回错误 `ToolResult`。

**错误处理示例**(工具内部):
```python
if "<body>" in html.lower():
    raise ValueError(
        "html contains forbidden tag <body>; "
        "请删除 <body> 后重新调用 show_widget"
    )
```

## WIDGET_SPEC

直接注入 `ToolDefinition.description`(LLM provider 将其作为 system message 的工具描述一次性发送):

```
## show_widget 设计规范(必须遵守)

### 1. 禁止项
- ❌ 渐变(streaming 时闪烁)
- ❌ box-shadow / blur / glow
- ❌ position: fixed(会逃出容器)
- ❌ 字体小于 11px
- ❌ <html> / <head> / <body> / <!DOCTYPE>
- ❌ HTML 注释 <!-- -->

### 2. 代码顺序(强制)
直接以 `<style>` 起始,紧接 HTML 结构,最后 `<script>`;不要写 `<head>` 包裹。
先到先渲染,JS 必须在 DOM 之后。

### 3. 坐标系(SVG 模式)
viewBox="0 0 680 H", width="100%"
宽度 680 固定,H 按内容自适应。所有 x 坐标基于 680。

### 4. CSS 变量(主题适配)
使用宿主注入的变量,不硬编码颜色。Framework 定义一组规范变量名,前端渲染时**把宿主实际变量值映射到规范名后注入 iframe**(这样 framework 契约稳定,scene 各自的命名互不影响):

- --color-background-primary / secondary
- --color-text-primary / secondary
- --color-border-primary / secondary
- --color-accent-primary

### 5. 外部资源
仅允许以下 CDN:
- cdnjs.cloudflare.com
- esm.sh
- cdn.jsdelivr.net
- unpkg.com

- ❌ 不要引用 Google Fonts (fonts.gstatic.com / fonts.googleapis.com)。CSP 已禁止;需要图标请用 cdnjs 上的 Material Icons / Font Awesome UMD 包

### 6. 复杂度预算
- 色系:最多 2 种
- 横向节点:最多 4 个(每个约 140px)
- 副标题:不超过 5 个词
- HTML 总大小:不超过 50KB
```

## 前端集成

### SSE 事件改动(events.py)

```python
if isinstance(evt, ToolExecutionStart):
    return {
        "event": "tool_start",
        "tool_name": evt.tool_name,
        "tool_call_id": evt.tool_call_id,  # 新增:前端按 id 定位 step,避免并行执行下错位
        "args": evt.args,
    }

if isinstance(evt, ToolExecutionEnd):
    result_dict = {
        "event": "tool_end",
        "tool_name": evt.tool_name,
        "tool_call_id": evt.tool_call_id,  # 新增:同上
        "result": _extract_result_text(evt.result),
        "is_error": evt.is_error,
    }
    # 透传 display 字段(仅成功路径会有 widget;失败走 raise,无 ToolResult)
    if (
        hasattr(evt.result, "display")
        and evt.result.display
        and "widget" in evt.result.display
    ):
        result_dict["display"] = evt.result.display
    return result_dict
```

(`ToolExecutionUpdate` 同样可加 `tool_call_id`,本次不强制。)

### 前端渲染(index.html)

**渲染位置决策**: widget 作为**当前 assistant message 气泡的直接子节点**插入(与 `.final-content` **同级**,按事件到达的时间顺序排列),不进入 `.final-content` 内部。理由:
- `renderFinalContent()` 通过 `finalDiv.innerHTML = html` 全量覆盖 `.final-content`;若 widget 插在其中,后续 `text_delta` 一次重渲染就会把 widget DOM 抹掉(HITL 卡片之所以安全,是因为 HITL 会阻断后续流;widget 不阻断,LLM 可继续输出"如上图所示...")
- widget 体积大(默认 400px 高),塞进紧凑的 tool step 列表会破坏视觉节奏
- 与 HITL 表单卡片"插入 assistant message 气泡"的总体路径一致,仅插入层级不同

收到 `tool_end` 事件且 `data.tool_name === "show_widget"` 时,**先于现有的 `tool_end` 处理逻辑**做分支(以 `else if` 链形式嵌入现有 SSE 事件分发器):

```js
} else if (data.event === 'tool_end' && data.display?.widget) {
    // 1. 让现有 tool step 仍标记为 done(用占位文本)
    //    用 tool_call_id 匹配 step,避免并行工具执行下找错 step
    //    (并行模式下多个 tool_start 先发,steps 中可能同时存在多个 running 的 tool step)
    const toolStep = steps.find(s => s.type === 'tool' && s.tool_call_id === data.tool_call_id);
    if (toolStep) {
        toolStep.detail = '[widget rendered]';
        toolStep.status = 'done';
        if (stepTimers[steps.indexOf(toolStep)]) {
            clearInterval(stepTimers[steps.indexOf(toolStep)]);
        }
        renderSteps();
    }
    // 2. 在 assistant 消息块内插入 widget 卡片
    ensureAssistantMsg();
    renderWidget(data.display.widget);
} else if (data.event === 'tool_end') {
    // …现有 tool_end 处理逻辑保持不动…
}
```

**前置要求**: 处理 `tool_start` 时,push 进 `steps` 的 step 对象必须带 `tool_call_id` 字段(从 `data.tool_call_id` 取),供 `tool_end` 反向匹配。

**renderWidget 流程**:

1. **先调 `flushRemainingType()`** — 把当前正在 typing 的 streaming 文本最终化进当前 `.final-content`,避免后续重渲染时还会移动 widget 前的文本
2. 创建容器 div + 标题标签(成功路径下才会被调用;失败走 raise → tool-error step)。**标题必须用 `titleEl.textContent = title` 设置,严禁使用 `innerHTML`** — LLM 可注入任意字符串到 `title` 参数,直接拼入 innerHTML 会在宿主 DOM 中触发 XSS
3. 创建 `<iframe sandbox="allow-scripts">`(**不带 `allow-same-origin`**)
4. 构建 srcdoc: CSP meta + 映射后的 CSS 变量 + HTML 内容
5. `iframe.onload` 后做一次 `smoothScrollToBottom()`(CDN 库可能延迟撑开内容)
6. **`assistantMsg.appendChild(widgetBlock)`** — 作为 `.final-content` 的兄弟节点插入到 assistant 气泡末尾,**不是** `.final-content` 内部
7. 调用 `registerWidget(iframe)` 注册到 `widgetFrames`,供 v2 sendPrompt 校验来源
8. **调用新增 helper `startNewFinalContent()`** — 在 widget 之后追加一个新的空 `.final-content` div,供后续 `text_delta`/`renderFinalContent()` 写入(避免后续文本通过 `innerHTML = html` 抹掉 widget;新 `.final-content` 成为当前"活跃"容器,旧的保留为已凝固的历史)
9. **页面初始化时**(不在这里)调用一次 `window.addEventListener("message", handleWidgetMessage)`

**渲染位置补充**: 若当前没有 assistant 气泡(LLM 直接调用 widget 无文本),由 `ensureAssistantMsg()` 创建一个新气泡承载 widget。此时 `usage-info` 仍贴在该气泡末尾,视觉上 widget 即气泡主体。这是已知 tradeoff,v1 接受。

**多次连续 widget 调用**: LLM 同一轮调用多次 `show_widget`(中间无 `text_delta`)时,每次 widget 之间都会通过 `startNewFinalContent()` 插入一个空 `.final-content` div,产生多个空 div。视觉上无可见影响(空 div 不占布局空间),作为已知 tradeoff 接受。若未来要优化,可在 `startNewFinalContent()` 入口检查 `currentFinalContent` 是否为空,空则复用、不新建。

**CSP 策略**(通过 srcdoc 内 `<meta>` 注入):
```
default-src 'none';
script-src 'unsafe-inline' https://cdnjs.cloudflare.com https://esm.sh https://cdn.jsdelivr.net https://unpkg.com;
style-src 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://unpkg.com;
img-src https: data:;
font-src https://cdnjs.cloudflare.com https://cdn.jsdelivr.net data:;
connect-src 'none';
```

**说明**:
- `default-src 'none'` 比 `'unsafe-inline'` 更严格(白名单制,显式开放各资源类型)
- **不允许 `'unsafe-eval'`** — Chart.js / D3 / Mermaid 等主流库无需 eval。少数模板编译类库(如 Vue runtime compiler)受影响,这是已知 tradeoff
- `connect-src 'none'` — 禁止 widget 发起 fetch/WebSocket(防止数据外泄)
- `img-src https:` — 只允许 HTTPS 图片,阻止 HTTP 追踪像素和明文资源
- **`script-src` 同时管控 ES Module 的 `import` 子加载**。若 LLM 使用 esm.sh 的 ESM 模式,所有 `import` 链路上的资源都必须在 `script-src` 白名单内。esm.sh 的 import 链可能跨多个域名(transitive deps),实际命中白名单的概率较低。**推荐 LLM 使用 cdnjs / jsdelivr 的 UMD 版本以简化加载链**
- 若 v2+ 需要 fetch,再按场景放开

**CSS 变量注入**:

宿主(`scene/http_sse/static/index.html`)使用的是 `--bg-primary` / `--text-primary` 等命名,但 framework 给 LLM 的规范是 `--color-background-primary` 等。前端渲染时**做一次映射**:

```js
// 宿主实际变量名 → framework 规范变量名
const VAR_MAPPING = {
  '--color-background-primary': '--bg-primary',
  '--color-background-secondary': '--bg-secondary',
  '--color-text-primary': '--text-primary',
  '--color-text-secondary': '--text-secondary',
  '--color-border-primary': '--border',
  '--color-border-secondary': '--border',
  '--color-accent-primary': '--accent',
};

const FALLBACKS = {
  // 暗色主题 fallback(匹配宿主 #0f0f23 背景),避免亮色卡片突兀出现在暗色页面上
  '--color-background-primary': '#0f0f23',
  '--color-background-secondary': '#1a1a2e',
  '--color-text-primary': '#e8e8f0',
  '--color-text-secondary': '#a0a0b8',
  '--color-border-primary': 'rgba(255,255,255,0.1)',
  '--color-border-secondary': 'rgba(255,255,255,0.06)',
  '--color-accent-primary': '#6366f1',
};

function buildCssVars() {
  const rootStyle = getComputedStyle(document.documentElement);
  const lines = [];
  for (const [specName, hostName] of Object.entries(VAR_MAPPING)) {
    const value = rootStyle.getPropertyValue(hostName).trim() || FALLBACKS[specName];
    lines.push(`${specName}: ${value};`);
  }
  return lines.join(' ');
}
```

注入方式:srcdoc 内内联 `<style>:root{${cssVars}}</style>`。映射表是 scene 层的实现细节,framework 不感知。

**iframe 隔离说明**:

`sandbox="allow-scripts"`(**不带 `allow-same-origin`**)的安全特性:
- iframe origin 为 `null`(opaque origin)
- 无法访问宿主 `document` / `localStorage` / `cookie`
- 无法通过 `parent.document` 移除 sandbox 属性
- 与宿主通信**只能通过 `postMessage`**(这是设计意图)
- CDN 库可正常加载并执行(srcdoc 内的脚本不受 origin 限制)

**为什么不开 `allow-same-origin`**:
官方文档明确警告 `allow-scripts + allow-same-origin` 组合**等于没有沙箱** — iframe 内脚本可读取宿主任意数据并移除 sandbox 属性。我们不能为了便利牺牲沙箱本质。`postMessage` 协议(v2 启用)足以覆盖回传需求。

**postMessage `origin` 校验**:
v2 实现 sendPrompt 时,宿主监听 `message` 事件必须检查 `event.source` 是 widget iframe 的 contentWindow(因为 origin 为 `null`,无法用 origin 字段校验,改用 source 引用比对)。

**PostMessage 协议**(v1: 监听器在**页面初始化时注册一次**,处理函数空实现):

```js
// Widget → Host
{ type: "send_prompt", text: "..." }

const widgetFrames = new WeakSet();
function registerWidget(iframe) { widgetFrames.add(iframe.contentWindow); }

function handleWidgetMessage(e) {
  if (!widgetFrames.has(e.source)) return;  // 必须用 source 校验
  if (e.data?.type === "send_prompt") {
    // v2 激活: 调用 sendMessage(e.data.text)
  }
}

// ⚠ 只在页面初始化时注册一次,不在每次收到 widget 事件时重复注册
window.addEventListener("message", handleWidgetMessage);
```

**v2 sendPrompt 校验强化**: v2 激活 sendPrompt 时,除 `widgetFrames.has(e.source)` 外,还需额外校验 `e.source.frameElement && document.contains(e.source.frameElement) && currentSessionId === iframeOwnedSessionId`。理由:`WeakSet` 中 `contentWindow` 在 iframe DOM 还存在时不会 GC,旧会话的 widget iframe 若未显式销毁,可能跨会话仍能通过单一 `has()` 校验向新会话注入消息。v1 监听器空实现不阻塞此场景,但 v2 实装时必须落实此双重校验。

**错误降级**:

v1 不做 iframe 内部错误检测(`srcdoc` 模式无法可靠检测内容错误:`onerror` 不触发,`documentElement` 即使 srcdoc 为空字符串也存在,检查恒为 true)。错误的可见反馈走两条路径:
1. **后端校验失败**: 工具 `raise ValueError` → loop 转为 `is_error=True` 的 `ToolExecutionEnd` → 前端走普通 tool-error step → LLM 看到错误自动重试
2. **iframe 内部运行时错误**(CDN 404、JS 异常等): v1 不处理,用户在浏览器 devtools 中可见

后端校验是唯一防线。仅在 `iframe.onload` 后调用一次 `smoothScrollToBottom()` 应对 CDN 异步加载导致的高度变化。

## 测试

`tests/tools/test_show_widget.py`:

1. **正常渲染**: `show_widget(html="<div>hi</div>")` → `display["widget"]["html"] == "<div>hi</div>"`
2. **禁止标签拦截**: 输入含 `<body>` → `pytest.raises(ValueError, match="forbidden tag")`,异常信息含 "请删除"
3. **大小限制**: HTML > 50KB → `pytest.raises(ValueError, match="size exceeds")`
4. **占位文本**: 正常路径下 `content[0].text` 以 `[widget rendered:` 开头
5. **height 边界**: `height=2000` → 实际存储为 1200;`height=None` → 400
6. **SSE 透传**: 模拟成功 `ToolExecutionEnd` → `agent_event_to_sse_json` 输出含 `display.widget`;模拟异常路径(loop 生成的 `is_error=True` 事件)→ 不含 `display`
7. **无污染**: 普通 tool(如 read_file)的 `tool_end` 事件不含 `display` 键(回归测试)
   *实现方式*: 直接构造 `ToolExecutionEnd(result=ToolResult(content=[TextContent(text='ok')], display=None))` 喂给 `agent_event_to_sse_json`,断言输出 dict 不含 `"display"` 键。无需走完整 agent loop。
8. **ToolDefinition 形态**: 断言 `WIDGET_SPEC in tool.definition.description`(子串包含),不做全文 equality 比较,避免 markdown / emoji / 空白漂移导致测试脆弱。同时断言 `tool.definition.prompt_snippet is None`(由 `extract_snippet` fallback 到 description 首句)

前端:手动验证(启动 http_sse,让 LLM 调用 show_widget;另测一个 `<body>` 错误用例确认 LLM 收到错误后会重试;测一次含 CDN script 的 widget 确认 iframe.onload 后滚动正常)。

## 改动文件

| 文件 | 操作 | 约行数 |
|---|---|---|
| `agent_core/tools/widgets/__init__.py` | 新建 | ~5 |
| `agent_core/tools/widgets/spec.py` | 新建 | ~50 |
| `agent_core/tools/widgets/tool.py` | 新建 | ~90 |
| `scene/http_sse/chat_assistant.py` | 修改 | +2(import + register) |
| `scene/http_sse/events.py` | 修改 | +4 |
| `scene/http_sse/static/index.html` | 修改 | +115 |
| `tests/tools/test_show_widget.py` | 新建 | ~90 |

**chat_assistant.py 改动示例**:
```python
from agent_core.tools.widgets import ShowWidgetTool
# ...
tool_registry.register(ShowWidgetTool())
```

**index.html 新增 helper 说明**: `startNewFinalContent()` 是本次新增的小函数(~15 行),职责是在当前 assistantMsg 末尾创建一个新的空 `.final-content` div,并把 `renderFinalContent()` / `flushRemainingType()` 的目标切换到这个新 div(通过更新模块级当前 final 容器引用)。每次插入 widget 后调用一次,确保后续 `text_delta` 写入新容器,旧 `.final-content` 凝固为历史,widget DOM 不再被 `innerHTML = html` 抹掉。

**实现要点(契约)**:
- 维护一个模块级变量 `currentFinalContent`(默认 = `ensureAssistantMsg()` 创建 assistant 气泡时所建的初始 `.final-content` div 的引用;`ensureAssistantMsg` 中创建该 div 后必须**同步赋值 `currentFinalContent`**)
- `startNewFinalContent()`:创建新的空 `.final-content` div,append 到当前 `assistantMsg`,并把 `currentFinalContent` 更新为该新 div
- 修改 `renderFinalContent()` 内部:把通过 `assistantMsg.querySelector('.final-content')` 的查找改为直接使用 `currentFinalContent`(querySelector 只返回第一个匹配,widget 插入后会写入旧 div 而非新 div)
- 修改 `flushRemainingType()`:同上改用 `currentFinalContent`
- 切换 assistant 气泡(新的 `message_start` / 新一轮对话)时,`ensureAssistantMsg()` 必须把 `currentFinalContent` 重新指向新气泡的初始 final-content
- **HITL 卡片插入逻辑同样改造**:现有 `index.html:2247` 附近的 HITL 卡片插入代码使用 `assistantMsg.querySelector('.final-content')` 定位插入锚点,querySelector 只返回**第一个** final-content;widget 之后 `startNewFinalContent()` 追加了新 final-content,HITL 卡片会插到旧的、已凝固的 final-content(widget 之前),导致顺序错乱。必须从 `querySelector('.final-content')` 改为使用 `currentFinalContent`,保证多 final-content 模型下 HITL 出现在正确位置
- **共 5 处代码点须修改(ensureAssistantMsg / startNewFinalContent / renderFinalContent / flushRemainingType / HITL 卡片插入逻辑 `index.html:2247`),实施时全部对齐,不可遗漏**
- **风险说明**: 若同一轮 LLM 先调 show_widget 再触发 HITL(并行 + 后端任意回执顺序),原实现会把 HITL 塞到 widget 之前;修正后两者按 SSE 到达顺序正确排列

## 演进路线

| 阶段 | 内容 | 触发条件 |
|---|---|---|
| **v1(本次)** | 纯展示;iframe + CSP;一次性 HTML;预留 postMessage 监听器 | — |
| **v2** | 激活 `sendPrompt`: postMessage → 宿主调用 `Agent.prompt()` | v1 稳定后 |
| **v3** | 结构化 widget 类型(chart/form/video_player): `kind` 参数 + 专用前端组件,降低 token 消耗 | 高频 widget 模式出现 |
| **v4** | 流式 token-by-token 渲染(`ctx.on_update`);双向 RPC(widget 查询 Agent) | 需求驱动 |

## 目标浏览器

Chromium/Firefox 最新两个稳定版本。Safari < 15.4 未测试。

## 不在首版范围

- HTML 深度清洗(信任 iframe sandbox + 严格 CSP)
- widget 持久化(session store 通用处理 display 字段)
- 需要 `unsafe-eval` 的模板编译类库(Vue runtime compiler 等)
- widget 间通信
- widget 发起 fetch/WebSocket(CSP `connect-src 'none'`)
- CLI / voice_ws 场景适配
- sendPrompt 实际激活(v2)
- **iframe 高度自适应**(height 是静态值,JS 动态加载内容不会自动撑开)
- **`<a>` 链接点击行为**(在 iframe 内导航,替换当前 widget 内容;`target="_top"` 和 `target="_blank"` 因 sandbox 限制而失败)
- **历史会话刷新安全**: 刷新页面后历史 assistant 气泡不含 widget(因 JsonlStore 不持久化 display 字段),`currentFinalContent` 自然退化为单一 final-content,不触发 `startNewFinalContent`,对历史回放无副作用
- **abort 后到达的 widget tool_end**: 由现有 `isStreaming` 状态机丢弃,无需特殊处理
