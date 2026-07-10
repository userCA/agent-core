# Changelog

## 2026-06-30 — 多模态消息支持 + 微信风格输入交互重构

**需求**：
- ChatRequest 支持多模态消息（图片/音频/视频/文件），符合 API 规范 §9.1
- 输入区域参考微信交互，图片选择放入上拉抽屉，清空原有快捷指令按钮

**方案**：
- 后端新增 `ContentBlockInput` 模型，`ChatRequest.content` 字段，`_content_blocks_to_images()` 转换器
- 前端 `streamChat` 新增 `content` 参数，`sendMessage` 支持 `File[]` 并转 base64
- 工具抽屉清空 9 个快捷指令（搜索/代码对比/调试等），替换为微信风格媒体操作（相册/拍摄/文件）
- 图片预览缩略图显示在输入框上方，用户消息气泡显示附件图片

**改动范围**：
| 文件 | 改动 |
|------|------|
| `server.py` | 新增 `ContentBlockInput` 模型、`ChatRequest.content` 字段、`_content_blocks_to_images()` 转换逻辑、`message` 从必填改为可选（默认空串） |
| `chat_assistant.py` | `send_message()` 新增 `images` 参数，透传至 session/agent |
| `types.ts` | 新增 `ContentBlockInput` 接口、`ChatRequest.content` 字段 |
| `client.ts` | `streamChat` 新增 `content` 参数，body 携带多模态内容块 |
| `useSSE.ts` | 新增 `fileToBase64()` / `filesToContentBlocks()` 工具函数；`sendMessage` 支持 `File[]`，生成预览 URL |
| `H5ChatInput.tsx` | 移除独立图片按钮，新增 `pendingImages` 状态、预览行、`handleDrawerFiles` 回调；Props 签名改为 `(text, files?)` |
| `ToolDrawer.tsx` | 清空原 TOOLS 数组，替换为 3 个媒体操作（相册/拍摄/文件），各自隐藏 `<input type="file">` |
| `ToolDrawer.css` | 移除旧 `.td-tool` / `.td-header` 样式，新增微信风格 `.td-media-btn` / `.td-media-ic`（56px 圆形图标） |
| `H5ChatInput.css` | 新增 `.h5-image-preview-row` / `.h5-image-preview` / `.h5-image-remove` / `.h5-image-add` 样式 |
| `chat-store.ts` | `ChatMessage` 新增 `attachments?: string[]` 字段 |
| `MessageBubble.tsx` | 用户消息气泡渲染图片附件缩略图 |
| `MessageBubble.css` | 新增 `.user-attachments` / `.user-attachment-thumb` 样式 |

**影响**：
- H5 输入区域恢复为 `[+] [textarea] [↑]` 三按钮布局
- 点击 + 打开上拉抽屉，选择相册/拍摄/文件后图片显示为预览缩略图
- 发送时图片转 base64 通过 `content` 字段发送到后端
- 用户消息气泡上方显示附件图片缩略图

---
## 2026-06-30 — 推理过程与结果输出拆分为独立卡片

**问题**：
- 推理步骤（think/tool blocks）和最终输出（text/widget/video blocks）都在同一个 `.bubble-assistant` 内
- `TraceCard` 内部的 `.trace` 容器有自己的卡片样式（边框/背景/阴影/圆角），导致“卡片中嵌套卡片”的双重边框问题
- 所有内容塞进一张卡片，视觉上过于拥挤

**方案**：
- `MessageBubble.tsx` 中将 blocks 拆分为 `stepBlocks`（推理步骤）和 `contentBlocks`（输出内容），各自渲染为独立的 `.bubble-assistant` 气泡
- 两个气泡紧密贴合：上方气泡 `border-radius: 16px 16px 4px 4px`，下方气泡 `border-radius: 4px 4px 16px 16px`，`margin-bottom: -1px` 重叠边框
- `TraceCard` 嵌套在 `.bubble` 内时去除自身卡片样式（背景透明/无边框/无阴影/无圆角），与父气泡视觉统一

**改动范围**：
| 文件 | 改动 |
|------|------|
| `MessageBubble.tsx` | 拆分 blocks 为 step/content，渲染两个独立气泡 |
| `MessageBubble.css` | 新增 `.bubble-trace-only` / `.bubble-content-only` 样式 |
| `TraceCard.css` | 新增 `.bubble .trace` / `.bubble .trace-head` / `.bubble .trace-rail` / `.bubble .trace-content` 覆盖样式 |

**影响**：
- 有推理步骤 + 输出内容时，拆分为两张卡片（上：推理过程，下：结果输出）
- 仅有推理或仅有内容时，保持单卡片行为
- TraceCard 独立使用时仍保留原有卡片样式

---

## 2026-06-30 — 用户消息气泡最小宽度修复

**问题**：
- 用户消息气泡（`.bubble-user`）没有设置 `min-width`，纯靠内容撑宽度
- 短消息如“你是谁”（3个字）在 390px 屏幕上只有约 75px，视觉过于窄小

**方案**：
为 `.bubble-user` 添加 `min-width: 120px`，确保短消息气泡有合理的最小宽度

**改动范围**：
| 文件 | 改动 |
|------|------|
| `MessageBubble.css` | `.bubble-user` 添加 `min-width: 120px` |
| `h5.css` | `.h5-app-layout .bubble-user` 同步添加 `min-width: 120px` |

**影响**：
- 短消息气泡最小宽度 120px，不再过窄
- 长消息不受影响（内容宽度 > 120px 时 min-width 不生效）
- max-width: 72% 约束仍然保持

---

## 2026-06-30 — Markdown 字体统一修复

**问题**：
- `.markdown-body` 在 tokens.css 中显式设置了系统字体栈 (`-apple-system, BlinkMacSystemFont, ...`)
- 导致所有 AI 消息内容（Markdown 渲染）使用系统字体而非设计系统指定的 Ma Shan Zheng 书法字体
- 聊天页面字体与设计系统不统一

**方案**：
移除 `.markdown-body` 的 `font-family` 显式覆盖，使其继承 `body` 的 `var(--font-sans)`（Ma Shan Zheng 优先）

**改动范围**：
| 文件 | 改动 |
|------|------|
| `tokens.css` | `.markdown-body` 移除 `font-family: -apple-system, ...` 覆盖 |

**影响**：
- AI 消息内容字体从系统 sans-serif 变为 Ma Shan Zheng（与设计系统一致）
- 代码块和 inline code 仍使用 `var(--font-mono)`（不受影响）
- 英文文本仍通过 `@font-face` Latin override 渲染为 Arial（不受影响）

---

## 2026-06-30 — H5 Header 布局优化 + 代码块紧凑化 + 新建会话功能

**问题**：
- Header 缺少“新建会话”入口，进入会话后无法重置对话
- 新建会话和历史按钮挤在左侧视觉拥挤，宠物头像按钮占用右侧空间
- 代码块 header 行（语言标签 + “复制”文字按钮）在 390px 手机上占用过多垂直空间

**方案**：
1. Header 对称三区布局：左`[历史]` 中`[咪兔·在线(可点击唤起宠物)]` 右`[新建会话]`
2. 标题“咪兔”可点击唤起宠物抽屉，移除 header 右侧宠物头像按钮
3. 代码块去掉独立 header 行，复制按钮改为 28px 小图标 absolute 定位在右上角
4. 语言标签缩小为 10px inline badge 在代码块右下角

**改动范围**：
| 文件 | 改动 |
|------|------|
| `CompactHeader.tsx` | 新增新建会话按钮、标题可点击、移除宠物头像、流式时替换为停止按钮 |
| `CompactHeader.css` | 新增 `.h5-header-right`、`.h5-header-title-btn`，移除 `.h5-header-pet` |
| `App.tsx` | 新增 `handleNewChat` 回调 + `onNewChat` prop |
| `markdown.ts` | 代码块去掉 `.code-block-header`，复制按钮改为纯图标 |
| `Markdown.tsx` | 复制反馈改为 SVG 图标切换（clipboard→check） |
| `tokens.css` | 代码块 CSS 紧凑化：absolute 定位复制按钮、新增 `.code-lang-tag` |

**影响面**：Header 更简洁、代码块节省约 28px 垂直空间、新增会话管理能力

---

## 2026-06-30 — H5 页面尺寸对齐原型 + 宠物/工具抽屉定位修复

**问题**：
- 手机框架宽度 430px 与原型 `oriental-chat-journal.html` 的 390px 不一致
- `CompanionDrawer` 和 `AuthPanel` 使用 `position: fixed` 定位到浏览器视口而非手机框架，导致超出 APP 范围
- `ToolDrawer` 已在前轮修复，但 `CompanionDrawer` 遗漏

**根因/方案**：
1. `#root:has(.h5-app-layout)` 的 `max-width` 从 430px 改为 390px，与原型 `.phone-frame` 一致
2. `CompanionDrawer` 和 `AuthPanel` 从 `MotionConfig` 外层移入 `.h5-app-layout` 内部
3. `h5.css` 新增 `.cd-overlay`、`.cd-sheet`、`.h5-auth-backdrop` 的 `position: absolute` 覆盖

**改动范围**：
| 文件 | 改动 |
|------|------|
| `App.css` | `max-width: 430px` → `390px` |
| `App.tsx` | `CompanionDrawer`、`AuthPanel` 移入 `.h5-app-layout` 内部 |
| `h5.css` | 新增 `.cd-overlay/.cd-sheet`、`.h5-auth-backdrop/.h5-auth-panel` absolute 定位覆盖 |

**影响面**：所有抽屉组件（工具/宠物/认证）均限制在手机框架内，不再溢出到浏览器视口。

---

## 2026-06-30 — SuggestionPills 欢迎页隐藏 + 会话场景限制

**问题**：
- SuggestionPills（搜索认证、代码对比等硬编码开发工具按钮）在欢迎页也显示，但实际应仅在会话中展示
- 欢迎页的 prompt-grid 已随分类 tab 动态切换，与 SuggestionPills 功能重叠

**根因/方案**：
- `App.tsx` 中 `SuggestionPills` 无条件渲染，未区分欢迎页与会话状态
- 通过 `useChatStore` 获取 `messages.length > 0` 判断是否有会话，条件渲染 SuggestionPills

**改动范围**：
| 文件 | 改动 |
|------|------|
| `App.tsx` | 新增 `hasMessages` 状态，`SuggestionPills` 仅在 `hasMessages` 为 true 时渲染 |

**影响面**：欢迎页更简洁，仅显示分类相关的 prompt 卡片；会话中保留快捷操作按钮。

---

## 2026-06-30 — 消息卡片双层边框 + 工具面板定位修复

**问题**：
1. 助手消息卡片出现“双层边框”：`.bubble-assistant` 边框与内部 `.code-block-wrapper` 边框叠加
2. 工具面板（ToolDrawer）过大且超出手机框架，`position: fixed` 定位到视口而非手机框架

**根因/方案**：
- 双层：`.bubble-assistant` 和 `.code-block-wrapper` 各有独立 `border`，在 H5 手机布局中叠加显示
- 工具面板：`.td-sheet` 和 `.td-overlay` 使用 `position: fixed`，在手机模拟器中定位到全屏视口

**改动范围**：
| 文件 | 改动 |
|------|------|
| `h5.css` | `.bubble-assistant .code-block-wrapper` 移除边框和阴影；`.td-overlay/.td-sheet` 改为 `position: absolute` + `max-height: 55%` |
| `App.css` | `.h5-app-layout` 添加 `position: relative` 建立定位上下文 |

**影响面**：助手消息卡片单层边框显示；工具面板限制在手机框架内。

---

## 2026-06-30 — Header 标题修复 + Markdown 代码渲染白屏修复

**问题**：
1. Header `<h1>` 显示会话标题而非“咪兔”，导致长标题被截断
2. 输出包含代码块时页面白屏（React 崩溃）

**根因/方案**：
- `CompactHeader.tsx` 中 `title` 变量使用了 `currentSession.title`，应始终显示“咪兔”
- `markdown.ts` 中 `renderer.code` 使用了新式对象 API `{ text, lang }`，但已安装的 `marked` v12.0.2 仍使用旧式三参数 API `(code, infostring, escaped)`，导致 `text` 为 `undefined`，调用 `.replace()` 崩溃

**改动范围**：
| 文件 | 改动 |
|------|------|
| `CompactHeader.tsx` | `title` 始终为“咪兔”，移除 `useSessionStore` 依赖 |
| `markdown.ts` | `renderer.code` 改为 `(code: string, infostring?: string)` 旧式 API |

**影响面**：Header 始终显示应用名称；代码块不再导致白屏崩溃。

---

## 2026-06-30 — SSE v1 内容块生命周期合规 + 风格统一

**需求**：检查聊天首页选项可用性，保证整体风格统一，消息流式展示契合 API 规范。

**根因/方案**：
- 欢迎页 `scene-tab` / `prompt-card` 边框 1.5px 与原型 `border-2 border-ink` (2px) 不一致
- `useSSE.ts` 仅处理 `phase=delta`，忽略 `start` / `done`，不符合 SSE v1 三阶段规范
- 非文本 Content Block（image/audio/video/component）未处理

**改动范围**：
| 文件 | 改动 |
|------|------|
| `WelcomeScreen.css` | scene-tab + prompt-card 边框 1.5px → 2px |
| `useSSE.ts` | 完整实现 phase=start→delta→done 三阶段；新增 image/audio/video/component 处理 |

**影响面**：流式消息严格遵守 SSE v1 规范；欢迎页视觉与原型统一。

**欢迎页 16 个选项可用性**：全部 ✅（代码开发4项、日常办公4项、设计创意4项、深度研究4项，均有对应工具支持）。

---

## 2026-06-30 — DeepSeek V4 Flash 模型集成

**需求**：将 H5 场景默认模型从 MiniMax M2.7 切换为 DeepSeek V4 Flash。

**根因/方案**：
- MiniMax API 用量已达限额（429），需切换到更经济的 DeepSeek
- DeepSeek 使用 OpenAI 兼容 API，复用 `OpenAIProvider` 实现
- base_url: `https://api.deepseek.com`（不带 `/v1` 后缀）

**改动范围**：
| 文件 | 改动 |
|------|------|
| `.env` | 新增 `DEEPSEEK_API_KEY`，`AGENT_PROVIDER=deepseek`，`AGENT_MODEL=deepseek-v4-flash` |
| `scene/h5/chat_assistant.py` | 新增 deepseek auth 分支 + OpenAIProvider 配置（3 个模型：deepseek-v4-flash / deepseek-chat / deepseek-reasoner） |
| `scene/h5/server.py` | `/models` 端点新增 3 个 deepseek 选项 |

**影响面**：H5 场景默认使用 DeepSeek V4 Flash，128K 上下文，8192 max output tokens。

---

## 2026-06-30 — H5 错误处理优化

**需求**：修复 HTTP 500 报错体验 + 右上角图标不符合水墨风。

**改动**：
1. **后端错误传播**：`server.py` agent 循环失败后发送 `message.error` SSE 事件
2. **前端错误国际化**：`client.ts` 将 HTTP 状态码翻译为中文友好提示
3. **错误去重**：`useSSE.ts` 使用 `errorShownRef` 防止重复显示
4. **429 重试**：`client.ts` withRetry 支持 429 状态码自动重试
5. **图标替换**：`CompactHeader.tsx` 像素猫 → 天蓝色抽象水滴 SVG
6. **错误气泡样式**：`MessageBubble.css` 适配水墨风主题色

---

## 2026-06-29 — H5 水墨风原型全面复刻

**需求**：H5 页面尽全力复刻 `oriental-chat-journal.html` 原型。

**改动**：完成 25+ 项 CSS/组件修复，包括背景渐变 135deg、@font-face Latin 子集覆盖、Ma Shan Zheng 书法字体全局应用、2px border-ink 手绘边框、shadow-card 硬偏移阴影、gentleBounce 动画等。
