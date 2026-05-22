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

### 返回结构

```python
ToolResult(
    content=[TextContent(text=f"[widget rendered: {title or '未命名'}]")],
    display={
        "widget": {
            "version": 1,
            "html": <校验后的 html>,
            "title": title,
            "height": min(height or 400, 1200),
        }
    }
)
```

### 校验(后端轻量)

| 检查项 | 行为 |
|---|---|
| HTML 大小 > 50KB | 返回错误占位 + `display.widget.error` |
| 包含 `<html>` / `<head>` / `<body>` / `<!DOCTYPE>` | 同上 |
| 正常输入 | 正常返回,`display` 含 widget 元数据 |

**注意 1**: 不做 HTML 深度清洗。安全由 iframe sandbox + CSP 兜底,不重复造轮子。

**注意 2**: `ToolResult` 没有 `is_error` 字段(那是 `ToolExecutionEnd` 事件层的属性,由 loop 根据异常推断)。校验失败不抛异常,而是通过 `display.widget.error` 传递错误,前端据此渲染错误提示。

**错误返回示例**:
```python
ToolResult(
    content=[TextContent(text="[widget 渲染失败: 包含禁止标签 <body>]")],
    display={
        "widget": {
            "version": 1,
            "error": "contains_forbidden_tag",
            "tag": "body",
        }
    }
)
```

## WIDGET_SPEC

直接注入 `ToolDefinition.description`,不通过独立 `read_spec` 调用(避免 LLM 跳过)。

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
<style> → HTML 结构 → <script>
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

### 6. 复杂度预算
- 色系:最多 2 种
- 横向节点:最多 4 个(每个约 140px)
- 副标题:不超过 5 个词
- HTML 总大小:不超过 50KB
```

## 前端集成

### SSE 事件改动(events.py)

```python
if isinstance(evt, ToolExecutionEnd):
    result_dict = {
        "event": "tool_end",
        "tool_name": evt.tool_name,
        "result": _extract_result_text(evt.result),
        "is_error": evt.is_error,
    }
    # 透传 display 字段(含 widget 元数据,success 和 error 都透传)
    if (
        hasattr(evt.result, "display")
        and evt.result.display
        and "widget" in evt.result.display
    ):
        result_dict["display"] = evt.result.display
    return result_dict
```

### 前端渲染(index.html)

收到 `tool_end` 事件且 `display?.widget` 存在时:

1. 创建容器 div + 标题标签
2. 创建 `<iframe sandbox="allow-scripts">`(**不带 `allow-same-origin`**)
3. 构建 srcdoc: CSP meta + 映射后的 CSS 变量 + HTML 内容
4. 插入聊天流
5. 注册 `message` 事件监听器(预留 v2 sendPrompt 接口)

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

**错误降级渲染**:

前端检测到 `display.widget.error` 时,不创建 iframe,直接渲染错误提示卡片:

```
┌────────────────────────────────────┐
│ ⚠ Widget 渲染失败                  │
│ 原因: contains_forbidden_tag (body) │
└────────────────────────────────────┘
```

**注意**: `srcdoc` 模式下 `iframe.onerror` 不会触发(没有网络请求)。错误检测通过 `iframe.onload` 完成,在 load 后检查 `contentDocument` 是否正常(如 `documentElement` 是否存在)。若检查失败,降级渲染错误提示并移除 iframe。

## 测试

`tests/tools/test_show_widget.py`:

1. **正常渲染**: `show_widget(html="<div>hi</div>")` → `display["widget"]["html"] == "<div>hi</div>"`,`display["widget"].get("error") is None`
2. **禁止标签拦截**: 输入含 `<body>` → `display["widget"]["error"] == "contains_forbidden_tag"`,`tag == "body"`
3. **大小限制**: HTML > 50KB → `display["widget"]["error"] == "size_exceeded"`
4. **占位文本**: `content[0].text` 以 `[widget rendered:` 或 `[widget 渲染失败:` 开头
5. **SSE 透传(成功)**: 模拟 ToolExecutionEnd → `agent_event_to_sse_json` 输出含 `display.widget.html`
6. **SSE 透传(错误)**: error 情况下 `display.widget.error` 也能透传
7. **无污染**: 普通 tool(如 read_file)的 tool_end 事件不含 `display` 键(回归测试)

前端:手动验证(启动 http_sse,让 LLM 调用 show_widget;另测一个 `<body>` 错误用例确认降级渲染)。

## 改动文件

| 文件 | 操作 | 约行数 |
|---|---|---|
| `agent_core/tools/widgets/__init__.py` | 新建 | ~5 |
| `agent_core/tools/widgets/spec.py` | 新建 | ~50 |
| `agent_core/tools/widgets/tool.py` | 新建 | ~90 |
| `scene/http_sse/events.py` | 修改 | +4 |
| `scene/http_sse/static/index.html` | 修改 | +80 |
| `tests/tools/test_show_widget.py` | 新建 | ~90 |

## 演进路线

| 阶段 | 内容 | 触发条件 |
|---|---|---|
| **v1(本次)** | 纯展示;iframe + CSP;一次性 HTML;预留 postMessage 监听器 | — |
| **v2** | 激活 `sendPrompt`: postMessage → 宿主调用 `Agent.prompt()` | v1 稳定后 |
| **v3** | 结构化 widget 类型(chart/form/video_player): `kind` 参数 + 专用前端组件,降低 token 消耗 | 高频 widget 模式出现 |
| **v4** | 流式 token-by-token 渲染(`ctx.on_update`);双向 RPC(widget 查询 Agent) | 需求驱动 |

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
