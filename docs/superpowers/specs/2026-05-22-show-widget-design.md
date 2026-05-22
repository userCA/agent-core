# show_widget Tool Design

**Date:** 2026-05-22
**Status:** Approved

## Summary

Add `show_widget` as a standalone tool in `agent_core/tools/widgets/`. The tool accepts an HTML fragment from the LLM, returns it as structured metadata in `ToolResult.details`, and the `scene/http_sse` frontend renders it in an iframe with CSP isolation. First version is display-only; interaction (`sendPrompt`) is pre-wired but not activated.

No existing capabilities are modified.

## Architecture

```
agent_core/tools/widgets/
├── __init__.py          # exports ShowWidgetTool
├── tool.py              # ShowWidgetTool implementation
└── spec.py              # WIDGET_SPEC constant (injected into description)

scene/http_sse/events.py  # ~4 lines: transparent widget details passthrough
scene/http_sse/static/index.html  # ~60 lines: renderWidget + handleWidgetMessage
```

## Data Flow

```
LLM calls show_widget(html=..., title=..., height=...)
  → ShowWidgetTool.execute()
    → validate HTML (reject <html>/<head>/<body>/<!DOCTYPE>, size limit 50KB)
    → return ToolResult(
        content=[TextContent(text="[widget rendered: {title}]")],
        details={"widget": {"version": 1, "html": ..., "title": ..., "height": ...}}
      )
  → SSE: tool_end event carries "widget" key
  → Frontend: detect widget key → create iframe srcdoc → render
```

- `content[0].text` is a placeholder for the LLM context (no HTML pollution).
- `details["widget"]` is consumed only by the frontend.

## Tool API

```python
ShowWidgetTool(
    name="show_widget",
    description=<WIDGET_SPEC全文>,
    parameters={
        "type": "object",
        "properties": {
            "html": {
                "type": "string",
                "description": "Complete HTML fragment following the spec"
            },
            "title": {
                "type": "string",
                "description": "Optional display title"
            },
            "height": {
                "type": "integer",
                "description": "Optional iframe height in px (default 400, max 1200)"
            }
        },
        "required": ["html"]
    }
)
```

### Return Structure

```python
ToolResult(
    content=[TextContent(text=f"[widget rendered: {title or 'untitled'}]")],
    details={
        "widget": {
            "version": 1,
            "html": <validated html>,
            "title": title,
            "height": min(height or 400, 1200)
        }
    }
)
```

### Validation (backend, lightweight)

- HTML size: reject > 50KB
- Reject full-page tags: `<html>`, `<head>`, `<body>`, `<!DOCTYPE>`
- No HTML sanitization (trust iframe sandbox + CSP)

## WIDGET_SPEC

Injected directly into `ToolDefinition.description` (no separate read_spec call — avoids LLM skipping it).

```
## show_widget 设计规范（必须遵守）

### 1. 禁止项
- ❌ 渐变（streaming 时闪烁）
- ❌ box-shadow / blur / glow
- ❌ position: fixed（会逃出容器）
- ❌ 字体小于 11px
- ❌ <html> / <head> / <body> / <!DOCTYPE>
- ❌ HTML 注释 <!-- -->

### 2. 代码顺序（强制）
<style> → HTML 结构 → <script>
先到先渲染，JS 必须在 DOM 之后。

### 3. 坐标系（SVG 模式）
viewBox="0 0 680 H"，width="100%"
宽度 680 固定，H 按内容自适应。所有 x 坐标基于 680。

### 4. CSS 变量（主题适配）
使用宿主注入的变量，不硬编码颜色：
- --color-background-primary / secondary
- --color-text-primary / secondary
- --color-border-primary / secondary / tertiary
- --color-accent-primary

### 5. 外部资源
仅允许以下 CDN：
- cdnjs.cloudflare.com
- esm.sh
- cdn.jsdelivr.net
- unpkg.com

### 6. 复杂度预算
- 色系：最多 2 种
- 横向节点：最多 4 个（每个约 140px）
- 副标题：不超过 5 个词
- HTML 总大小：不超过 50KB
```

## Frontend Integration

### SSE Event Change (events.py)

```python
if isinstance(evt, ToolExecutionEnd):
    result_dict = {
        "event": "tool_end",
        "tool_name": evt.tool_name,
        "result": _extract_result_text(evt.result),
        "is_error": evt.is_error,
    }
    # Transparent passthrough for widget details
    if hasattr(evt.result, 'details') and evt.result.details and 'widget' in evt.result.details:
        result_dict["widget"] = evt.result.details["widget"]
    return result_dict
```

### Frontend Rendering (index.html)

On `tool_end` with `widget` key:

1. Create container div with title label
2. Create `<iframe sandbox="allow-scripts allow-same-origin">`
3. Build srcdoc: CSP meta tag + CSS variables from host + HTML content
4. Inject into chat stream
5. Register `message` event listener for future `sendPrompt` support

**CSP policy** (injected via `<meta>` in srcdoc):
```
default-src 'unsafe-inline' 'unsafe-eval';
script-src 'unsafe-inline' 'unsafe-eval' cdnjs.cloudflare.com esm.sh cdn.jsdelivr.net unpkg.com;
style-src 'unsafe-inline' cdnjs.cloudflare.com cdn.jsdelivr.net unpkg.com;
img-src * data:;
```

**CSS variable injection**: Extract a static mapping of core variables from the host page and inject as `:root{...}` in the srcdoc.

**PostMessage protocol** (v1: listener registered, handler empty):
```js
// Widget → Host
{ type: "send_prompt", text: "..." }
```

## Testing

`tests/tools/test_show_widget.py`:

1. Normal render: `show_widget(html="<div>hi</div>")` → details contains widget with html
2. Validation rejection: input with `<body>`/`<!DOCTYPE>`/`<html>` → is_error=True
3. Size limit: >50KB HTML → rejected
4. Placeholder text: `content[0].text` is `[widget rendered: ...]`
5. SSE passthrough: simulated ToolExecutionEnd → output contains `widget` key
6. No pollution: normal tool_end events do not contain `widget` key

Frontend: manual verification only (start http_sse, prompt LLM to call show_widget).

## Files Changed

| File | Action | Lines |
|---|---|---|
| `agent_core/tools/widgets/__init__.py` | New | ~5 |
| `agent_core/tools/widgets/spec.py` | New | ~50 |
| `agent_core/tools/widgets/tool.py` | New | ~80 |
| `scene/http_sse/events.py` | Modify | +4 |
| `scene/http_sse/static/index.html` | Modify | +60 |
| `tests/tools/test_show_widget.py` | New | ~80 |

## Evolution Roadmap

| Phase | Content | Trigger |
|---|---|---|
| **v1 (this)** | Display-only; iframe + CSP; one-shot HTML; pre-wired postMessage listener | — |
| **v2** | Activate `sendPrompt`: postMessage → host calls `Agent.prompt()` | v1 stable |
| **v3** | Structured widget types (chart/form/video_player): `kind` param, dedicated frontend components, lower token cost | After high-frequency widget patterns emerge |
| **v4** | Streaming token-by-token render (`ctx.on_update`); bidirectional RPC (widget queries agent) | Demand-driven |

## Out of Scope (v1)

- HTML sanitization (trust iframe + CSP)
- Widget persistence (session store handles details generically)
- Fine-grained CSS variable extraction (static mapping is sufficient)
- Inter-widget communication
- CLI / voice_ws scene adaptation
