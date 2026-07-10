# Release Notes

## 2026-06-30 (v14)

### 多模态消息支持 + 微信风格输入交互

- **发送图片**：点击输入框左侧 + 按钮，打开上拉抽屉，选择相册、拍摄或文件即可添加图片
- **图片预览**：选中的图片显示为 64×64 缩略图，支持删除和追加（最多 9 张）
- **微信风格抽屉**：工具抽屉已清空原有快捷指令（搜索/代码对比/调试等），替换为相册、拍摄、文件三个媒体操作
- **用户消息附件**：发送图片后，用户消息气泡上方显示附件图片缩略图
- **后端多模态 API**：`POST /chat/stream` 现在支持 `content` 字段，接受 text/image/audio/video/file 类型的内容块

---
## 2026-06-30 (v13)

### H5 场景 API 规范对齐与修复

**Critical 修复：**
- **心跳事件**：server.py 每 15s 发送 `heart` 事件保持连接活跃，符合规范 15-30s 要求
- **Streaming Markdown 去重修复**：events.py 添加内部缓冲区处理跨 delta 的部分图片 Markdown，避免重复渲染

**Warning 修复：**
- **会话重载图片恢复**：chat-store.ts 在加载历史记录时自动重建图片生成工具的 image 块
- **step 事件分发**：useSSE.ts 修复 step.start/step.end 事件分发逻辑，改用 actionType 而非 type 字段
- **图片回复占位符**：图片-only 回复使用“已生成媒体内容”而非 "(empty)"
- **response.body 空值检查**：client.ts 添加 SSE 响应体空值保护
- **SSE buffer 残留处理**：sse-parser.ts 在流结束时处理缓冲区残留数据
- **setStreamBlocks 节流**：useSSE.ts 使用 requestAnimationFrame 节流块同步，避免每个 delta 都触发全量重渲染
- **错误码标准化**：server.py 使用 E00008/E00009 等规范错误码
- **file Content Block**：useSSE.ts 支持 file 类型内容块处理
- **URL scheme 验证**：events.py 图片 URL 提取时验证 http/https 协议

**优化：**
- **类型安全**：useSSE.ts 移除多处 `as any` 类型转换，改用 _Block 接口属性访问
- **Tracker close() 重置**：events.py 的 `_ContentTracker.close()` 重置 `_open_index` 为 -1

**规范对齐（第二轮）：**
- **message.end usage 省略**：usage 为 null 时不再发送该字段，符合规范示例格式
- **message.error messageId**：错误事件使用 `msg_{sessionId}` 格式，替代硬编码 `msg_err`

---

## 2026-06-30 (v12)

### 图片内容块前后端对接优化

- **后端 image content block 发射**：H5 events.py 在 ToolExecutionEnd 时自动提取图片 URL，发射 image content block（快照模式 start + done）
- **Markdown 去重**：后端自动剥离文本流中的 `![...](url)` 图片 Markdown，避免双重渲染
- **display.image 载荷**：agnes_image_tool.py 的 ToolResult 新增 display.image 字段，包含 url/size 信息
- **前端 ImageDisplay 类型**：types.ts 新增 ImageDisplay 接口，DisplayPayload 支持 image 字段
- **MessageBlock image 类型**：chat-store.ts 新增 'image' 块类型和 imageUrl/imageMeta 字段
- **useSSE image 处理**：image content block 不再降级为 Markdown 文本，而是作为专用图片块处理
- **TraceCard 图片渲染**：推理卡片和内容卡片均支持图片块渲染，`<img>` 标签配合水墨风样式
- **MessageBubble 图片分类**：image 块归入内容卡片而非推理卡片

---

## 2026-06-30 (v11)

### 推理过程与结果输出拆分卡片

- **卡片拆分**：推理步骤和最终输出现在渲染为两张独立的气泡卡片，不再全部塞进一张卡片
- **紧密贴合**：上下两张卡片通过 border-radius 互补和 margin 重叠实现无缝连接
- **去除双重边框**：TraceCard 嵌套在气泡内时不再显示自己的边框/背景/阴影
- **向下兼容**：仅有推理或仅有内容时保持单卡片行为

---

## 2026-06-30 (v10)

### 用户消息气泡宽度优化

- **最小宽度保证**：用户消息气泡新增 `min-width: 120px`，短消息（如“你是谁”“你好”）不再过窄
- **长消息不受影响**：内容较多时仍按 72% 最大宽度自适应
- **视觉统一**：与主流聊天应用（微信、Telegram）的气泡宽度行为一致

---

## 2026-06-30 (v9)

### 字体统一修复

- **AI 消息字体统一**：聊天页面所有文本内容（包括 Markdown 渲染的 AI 消息）现在统一使用 Ma Shan Zheng 书法字体，与设计系统一致
- **修复原因**：之前 `.markdown-body` 显式设置了系统字体，导致 AI 消息内容跳过了设计系统的字体栈
- **英文不受影响**：`@font-face` Latin override 仍然生效，英文文本渲染为 Arial

---

## 2026-06-30 (v8)

### Header 布局优化

- **新建会话功能**：会话中顶部右侧出现编辑图标，点击清空消息并恢复欢迎页
- **对称三区布局**：左`[历史]` 中`[咪兔·在线]` 右`[新建会话]`，标题可点击唤起宠物
- **移除宠物头像按钮**：宠物唤起改为点击标题，Header 更干净

### 代码块紧凑化

- **去掉独立 header 行**：语言标签 + “复制”文字按钮不再占用整行
- **复制图标浮动**：28px 小图标 absolute 定位在代码块右上角，默认半透明，悬停显示
- **语言标签**：缩小为 10px inline badge 在右下角
- **节省空间**：每个代码块减少约 28px 垂直高度

---

## 2026-06-30 (v6)

### 布局修复

- **手机框架宽度对齐原型**：从 430px 调整为 390px，与 `oriental-chat-journal.html` 原型的 `.phone-frame` 一致
- **宠物抽屉不再溢出**：`CompanionDrawer` 和 `AuthPanel` 移入 `.h5-app-layout` 内部，使用 `position: absolute` 定位，限制在手机框架内
- **工具抽屉 + 认证面板**：同步确认在框架内正确显示

---

## 2026-06-30 (v5)

### 体验优化

- **欢迎页更简洁**：移除底部的硬编码快捷操作按钮（搜索认证、代码对比等），仅保留与当前分类相关的 prompt 卡片
- **会话中保留快捷操作**：进入会话后，底部显示快捷操作药丸按钮（搜索认证、代码对比、运行测试等）

---

## 2026-06-30 (v4)

### Bug 修复

- **消息卡片双层边框**：助手消息中的代码块不再显示双层边框，视觉更简洁
- **工具面板溢出**：工具面板现在限制在手机框架内，不再超出操作界面

---

## 2026-06-30 (v3)

### Bug 修复

- **Header 标题**：修复 Header 显示会话标题而非“咪兔”的问题，长标题不再被截断
- **代码块白屏**：修复输出包含代码块时页面白屏崩溃的问题（marked v12 API 不匹配）

---

## 2026-06-30 (v2)

### 功能优化

- **流式消息 API 合规**：严格遵循 SSE v1 规范的三阶段内容块生命周期（start → delta → done）
- **多媒体内容块支持**：新增 image/audio/video/component 类型的内容块处理
- **欢迎页风格统一**：所有按钮边框统一为 2px，与原型手绘风一致

### 欢迎页可用性

- 全部 16 个快捷选项均可用，覆盖代码开发、日常办公、设计创意、深度研究四大分类

---

## 2026-06-30

### 新增功能

- **DeepSeek 模型支持**：新增 DeepSeek V4 Flash / Chat / Reasoner 三个模型选项
- **默认模型切换**：H5 场景默认使用 DeepSeek V4 Flash（128K 上下文）
- **中文错误提示**：网络错误、服务不可用等场景显示友好中文提示
- **429 自动重试**：请求过于频繁时自动重试

### 视觉改进

- **水墨风全面复刻**：背景渐变、书法字体、手绘边框、硬偏移阴影等 25+ 项样式还原
- **右上角图标**：替换为水墨风天蓝色抽象水滴 SVG
- **错误气泡样式**：墨色淡底 + 藤紫淡边 + 书法字体

### 修复

- HTTP 500 错误现在正确显示"服务暂时不可用，请稍后重试"
- 错误消息不再重复显示
- 空内容+错误时不再添加空助手消息
