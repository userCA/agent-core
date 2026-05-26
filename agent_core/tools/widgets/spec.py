"""WIDGET_SPEC — the show_widget design spec injected into ToolDefinition.description."""

WIDGET_SPEC = """## show_widget 设计规范(必须遵守)

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
使用宿主注入的变量,不硬编码颜色:

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
- HTML 总大小:不超过 50KB"""
