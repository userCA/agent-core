---
name: 咪兔 MiTu
description: 有温度的 AI 伙伴 — ASCII 手作美学遇见柔和陪伴感
colors:
  warm-paper:
    value: "#fdfcfc"
  warm-charcoal:
    value: "#201d1d"
  soft-cloud:
    value: "#f8f7f7"
  warm-porcelain:
    value: "#f1eeee"
  muted-iron:
    value: "#646262"
  warm-slate:
    value: "#424245"
  weathered-stone:
    value: "#6e6e73"
  ash-gray:
    value: "#595959"
  companion-blue:
    value: "#007aff"
  companion-blue-hover:
    value: "#0056b3"
  rose:
    value: "#ff3b30"
  rose-deep:
    value: "#d70015"
  honey:
    value: "#ff9f0a"
  sage:
    value: "#30d158"
  pastel-rose-bg:
    value: "#FDEBEC"
  pastel-rose-text:
    value: "#9F2F2D"
  pastel-sky-bg:
    value: "#E1F3FE"
  pastel-sky-text:
    value: "#1F6C9F"
  pastel-sage-bg:
    value: "#EDF3EC"
  pastel-sage-text:
    value: "#346538"
  pastel-honey-bg:
    value: "#FBF3DB"
  pastel-honey-text:
    value: "#956400"
typography:
  display:
    fontFamily: "Newsreader, Playfair Display, Lyon Text, Instrument Serif, serif"
    fontWeight: 400
    lineHeight: 1.15
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica Neue, Arial, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "JetBrains Mono, IBM Plex Mono, ui-monospace, SF Mono, Menlo, Monaco, Consolas, PingFang SC, Microsoft YaHei, monospace"
    fontSize: "11px"
    fontWeight: 500
    letterSpacing: "0.04em"
rounded:
  sm: "4px"
  md: "8px"
  lg: "12px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.warm-charcoal}"
    textColor: "{colors.warm-paper}"
    rounded: "{rounded.sm}"
    padding: "6px 14px"
  button-primary-hover:
    backgroundColor: "{colors.companion-blue}"
    textColor: "{colors.warm-paper}"
  button-default:
    backgroundColor: "{colors.warm-paper}"
    textColor: "{colors.warm-charcoal}"
    rounded: "{rounded.sm}"
    padding: "6px 14px"
  button-default-hover:
    backgroundColor: "{colors.warm-porcelain}"
  button-danger:
    backgroundColor: "{colors.warm-paper}"
    textColor: "{colors.rose}"
    rounded: "{rounded.sm}"
    padding: "6px 14px"
  button-danger-hover:
    backgroundColor: "{colors.pastel-rose-bg}"
  chip-pastel:
    backgroundColor: "{colors.pastel-sky-bg}"
    textColor: "{colors.pastel-sky-text}"
    rounded: "{rounded.md}"
    padding: "2px 10px"
  input-field:
    backgroundColor: "{colors.warm-paper}"
    textColor: "{colors.warm-charcoal}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
---

# Design System: 咪兔 MiTu

## 1. Overview

**Creative North Star: "Handmade Digital"**

咪兔的视觉系统建立在一个张力之上：**ASCII 终端美学的克制精准** 与 **陪伴关系的温暖触感** 之间的平衡。每一帧精灵是手写 ASCII art；每一个交互反馈是刻意的手工感。这不是 machine aesthetic 的冷峻极简，也不是 consumer app 的甜美圆润 — 而是像素级的手工关怀，像一本精心排版的代码诗集。

系统拒绝将 AI 产品包装成冰冷的高效工具，也不滑向可爱的卡通风格。温暖来自细节：暖色调的中性色（红底灰而非纯灰）、单色精灵以外的柔和粉彩标记、按压时有缩放反馈的按钮。严肃的技术能力（流式推理、工具调用、多专家并行）与情绪化的精灵陪伴共存。

**Key Characteristics:**
- ASCII craft over vector polish
- Warm-tinted neutrals over cold grays
- Pastel accents used as category markers, not decoration
- Soft tactile feedback — buttons press, pages fade,精灵眨眼
- Monospace as warmth, not coldness — the terminal as a handmade object

## 2. Colors: The Soft Pastel Companion Palette

暖调中性色为主画布，单一蓝色强调功能交互，柔和粉彩四色系为分类/标记/状态提供可扩展的视觉语言。

### Primary
- **Companion Blue** (`#007aff`): 唯一的功能强调色。用于链接、焦点环、主按钮悬停、选中状态。在亮色模式下是 iOS 蓝的继承，在暗色模式下被 `#409cff` 覆盖。克制使用 — 一个屏幕内不超过 10% 的像素应使用此色。
- **Companion Blue (Dark)** (`#409cff`): 暗色主题下的蓝色强调，亮度提升以保持对比度。

### Neutral
- **Warm Paper** (`#fdfcfc`): 主画布背景。不是纯白 — 带有几乎不可察觉的暖红底色（chroma 0.005）。亮色模式下承载 80% 以上的表面积。
- **Warm Charcoal** (`#201d1d`): 主文本色。近黑但保持暖调（hue ~15°），避免纯黑的 harshness。也是主按钮填充和深色表面的底色。
- **Soft Cloud** (`#f8f7f7`): 次要背景 — 侧边栏、代码块头部、表头。比画布深半阶，区分区域而不引入边框。
- **Warm Porcelain** (`#f1eeee`): 悬停态和选中态的背景。代码背景、按钮按下态。比 Soft Cloud 再深半阶。
- **Warm Slate** (`#424245`): 正文文本。不纯黑，保留暖调。
- **Muted Iron** (`#646262`): 次要文本、强边框。scrollbar 滑块。
- **Weathered Stone** (`#6e6e73`): 三级文本、代码语言标签。
- **Ash Gray** (`#595959`): placeholder 文本、禁用态。

### Semantic
- **Rose** (`#ff3b30`): 危险/删除/错误。边框和文字使用；背景使用其 6% 透明变体。
- **Honey** (`#ff9f0a`): 警告。仅用于需要引起注意但非错误的状态。
- **Sage** (`#30d158`): 成功/完成。用于复制成功、完成标记。

### Pastel Family (Category & Status Markers)
四个柔和粉彩色系用于技能分类、连接器类型、状态标签、筛选选项卡：

- **Rose** — 背景 `#FDEBEC`，文字 `#9F2F2D`
- **Sky** — 背景 `#E1F3FE`，文字 `#1F6C9F`
- **Sage** — 背景 `#EDF3EC`，文字 `#346538`
- **Honey** — 背景 `#FBF3DB`，文字 `#956400`

每个粉彩色提供 bg + text 配对，保证 4.5:1 以上的对比度。粉彩标记使用等宽字体 11px 标签样式，8px 圆角。

### Thematic Accent (Companion-Derived)
精灵的 7 个品种提供了一套可选的辅助色调：橘虎斑的暖橙、燕尾服的黑白对比、三花的玳瑁色、暹罗的奶油棕、黑猫的墨灰、布偶的蓝灰、苏格兰折耳的银灰。这些不设为 token，但作为氛围参考 — 新页面或功能可从中提取独特色调。

### Named Rules
**The One Blue Rule.** Companion Blue 是唯一的函数式强调色。不在同一界面引入第二个功能蓝（不用 teal/indigo/purple accent）。粉彩色系仅用于非交互的分类标记，不参与功能层级。

**The Warm Neutral Rule.** 所有灰色必须带暖调底色（hue 15-30°，chroma ≥ 0.003）。纯灰（chroma 0）禁止。这是手作感的色彩基础。

## 3. Typography

**Display Font:** Newsreader, Playfair Display, Lyon Text, Instrument Serif, serif
**Body Font:** system sans stack (-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica Neue, Arial, PingFang SC, Microsoft YaHei)
**Label/Mono Font:** JetBrains Mono, IBM Plex Mono, ui-monospace, SF Mono, consolas

**Character:** Serif display 仅在欢迎页品牌名使用，带来编辑感的手作温度。System sans body 保证 14px 正文的清晰度和中文渲染质量。Mono label 是系统的标志性特征 — 标签、分类、代码、精灵全部使用等宽，将"终端感"注入 UI 的毛细血管。

### Hierarchy
- **Display** (Regular 400, 28-36px, 1.15): 登录页"咪兔"品牌名。仅在欢迎屏幕出现。serif。
- **Headline** (Bold 700, 16px, 1.4): 页面标题、侧边栏分区标题。sans。
- **Title** (Semibold 600, 15px, 1.4): 卡片标题、消息角色标签、对话名称。
- **Body** (Regular 400, 14px, 1.6, max 72ch): 所有正文、消息气泡、设置描述。系统默认字号。
- **Label** (Medium 500, 11px, 1.4, 0.04em tracking): 分类标记、时间戳、代码语言、状态徽章。mono。仅大写英文场景使用 uppercase 变换。

### Named Rules
**The Mono Thread Rule.** 等宽字体是系统的触觉线索。所有非正文短文本（标签、时间、分类、技术标识）必须使用 font-mono。它让终端美学穿透每个 UI 元素，而非仅停留在精灵和代码块。

**No Pure Hierarchy Rule.** 不在同一页面使用超过 3 种字号。层级通过 weight + color 对比传达，而非字号膨胀。正文 14px，标题 15-16px，品牌 28-36px — 中间不加步阶。

## 4. Elevation

本系统优先使用**色调分层**（tonal layering）来表达深度：canvas → surface-soft → surface-card 的明度阶梯提供清晰的空间感，不需要阴影。阴影是选项，不是默认。

**场景导向的阴影使用：**
- **页面内容区** — 纯色调分层，无阴影。内容本身就是焦点。
- **Hover 态** — 极轻阴影 (`0 2px 8px rgba(0,0,0,0.04)`) 或仅通过 border-color 变化表示可交互性。
- **Modal / Dialog** — backdrop (`rgba(0,0,0,0.35)`) 提供唯一的强深度线索。modal 面板自身无阴影，靠色调和 backdrop 对比完成分层。
- **Toast** — 无阴影，靠边框 + backdrop 区分。

暗色主题下分层反转：surface-dark 最底层，canvas/surface-soft/surface-card 逐级提亮。

### Named Rules
**The Tonal First Rule.** 在添加阴影前，先用色调明度差表达层级。如果表面与画布的明度差 ≥3%，不需要阴影。阴影仅在无法用明度区分时引入（如 modal 需要与下方内容切断视觉连接）。

## 5. Components

所有组件使用 4px 圆角（`--radius-sm`）作为默认，8px（`--radius-md`）用于标签/徽章。交互元素最小触摸目标 44px（移动端）。

### Buttons
软触感。按压时 `transform: scale(0.98)` 给予物理反馈。

- **Shape:** 4px 圆角（`--radius-sm`），1px 边框
- **Primary:** Warm Charcoal 填充 + Warm Paper 文字。Hover 时变为 Companion Blue 填充以提供愉悦的色彩惊喜。
- **Default:** Warm Paper 填充 + 1px hairline 边框。Hover 时 border 变为 hairline-strong，背景不变。
- **Danger:** 透明填充 + Rose 边框 + Rose 文字。Hover 时出现 6% Rose 背景。
- **Transition:** `border-color 0.15s ease, background 0.15s ease, transform 0.1s ease`

### Chips / Tags
柔和粉彩标记系统。用于技能类型、连接器类别、筛选条件、状态指示。

- **Shape:** 8px 圆角（`--radius-md`），无边框
- **Fill:** 对应粉彩色系 bg（如 pastel-sky-bg）
- **Text:** 对应粉彩色系 text（如 pastel-sky-text）
- **Typography:** 11px mono, 500 weight, 0.04em tracking
- **Padding:** 2px 10px

### Cards / Surfaces
系统不使用传统"卡片"概念。内容区域由色调分层表达，而非带阴影/圆角的卡片容器。

- **Sidebar:** Soft Cloud 背景，hairline 右边框。与主内容区通过明度差区分。
- **Message Bubbles:** 用户消息使用 Warm Charcoal 填充（亮色模式），助手消息无背景仅文字。不使用圆角卡片包裹 — 气泡是扁平的背景色块。
- **Code Blocks:** Warm Porcelain 背景，1px hairline 全边框，4px 圆角。头部带语言标签和复制按钮。

### Inputs
- **Shape:** 4px 圆角，1px hairline 边框
- **Background:** Warm Paper
- **Focus:** 2px Companion Blue 外环（`outline-offset: 2px`）
- **Placeholder:** Ash Gray 色文字
- **Transition:** `border-color 0.15s ease`

### Navigation (Sidebar)
- **Width:** 260px 展开，52px 折叠（仅图标）
- **Background:** Soft Cloud
- **Active Item:** Warm Porcelain 背景 + Warm Charcoal 文字
- **Inactive Item:** 无背景，Warm Slate 或 Muted Iron 文字
- **Hover:** Warm Porcelain 背景过渡
- **Typography:** 14px system sans, 图标 18px inline SVG
- **Mobile:** `< 768px` 时默认折叠，overlay 模式展开

### Companion Sprite (Signature)
系统的标志性组件 — ASCII 猫形精灵，7 品种、5 情绪、3 帧动画。

- **Render:** `<pre>` 标签，mono 字体，固定字符网格
- **Size:** 头部小型（仅显示前 3 行），登录页完整尺寸
- **Animation:** CSS `@keyframes` 循环切换 3 帧，约 0.4s/帧，根据情绪调整间隔（sleeping 更慢）
- **Interaction:** 情绪由后端 FSM 驱动，前端仅做帧动画。稀有度星标、闪亮粒子为 CSS overlay
- **Accent:** 精灵眼睛颜色独立于系统强调色，品种决定眼睛色

### Modals / Dialogs
模态是最后选择。优先使用 inline expansion、tooltip、或页面内切换。

- **Backdrop:** `rgba(0,0,0,0.35)`，点击关闭
- **Panel:** Warm Paper 背景，无阴影，1px hairline 全边框
- **Animation:** spring 进入（Motion `spring` preset），0.12s opacity exit
- **Focus Trap:** focus 锁定在 modal 内，esc 关闭

## 6. Do's and Don'ts

### Do:
- **Do** 使用暖调中性色。每个"灰色"必须带暖底（hue ~15-30°），chroma ≥ 0.003。
- **Do** 用 Mono 字体标注所有短文本 — 标签、时间戳、分类、状态。等宽是手作感的纹理。
- **Do** 优先用色调明度差（≥3%）表达层级，阴影是辅助手段。
- **Do** 用柔和粉彩 bg+text 配对标记分类/状态，保证 4.5:1 对比度。
- **Do** 在交互元素上保留 `transform: scale(0.98)` 按压反馈 — 触感的"手作"体现。
- **Do** 保持 Companion Blue ≤10% 的屏幕像素占比。它的稀缺性是它有效的理由。
- **Do** 默认 4px 圆角，标签类 8px。不混合多种圆角值。
- **Do** 精灵是视觉锚点，不是装饰。每个页面至少保留一个精灵存在点（头部或角落）。

### Don't:
- **Don't** 使用纯黑（`#000`）或纯白（`#fff`）。违反 Warm Neutral Rule。
- **Don't** 引入第二个功能强调色（teal/purple/indigo accent）。粉彩 ≠ 功能色。
- **Don't** 在页面布局中使用阴影卡片。色调分层面板，不要卡片堆叠。
- **Don't** 将 modal 作为第一反应。优先考虑 inline 展开、tooltip、页面内切换。
- **Don't** 使用渐变文字（`background-clip: text`）。
- **Don't** 使用侧边条纹边框（`border-left` > 1px 作为彩色强调）。
- **Don't** 用超过 3 种字号在同一页面。通过 weight + color 建立层级。
- **Don't** 把产品做成冷冰冰的开发者工具面板。即使是最技术的设置页，也应保留温暖和陪伴感 — 这是 PRODUCT.md 的核心承诺。
