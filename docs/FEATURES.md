# H5 Features Status

## 模型支持

| Provider | Model | Status | Context | Max Output |
|----------|-------|--------|---------|------------|
| **DeepSeek** | deepseek-v4-flash | ✅ **默认** | 128K | 8192 |
| **DeepSeek** | deepseek-chat | ✅ 可用 | 64K | 8192 |
| **DeepSeek** | deepseek-reasoner | ✅ 可用 | 64K | 8192 |
| MiniMax | minimax-m2.7 | ⚠️ 限额 | 256K | 4096 |
| Agnes | agnes-2.0-flash | ✅ 可用 | 256K | 65536 |
| OpenAI | gpt-4o | 需配置 | - | - |
| Anthropic | claude-sonnet-4 | 需配置 | - | - |

## H5 前端功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 水墨风视觉系统 | ✅ 完成 | 原型像素级还原（背景渐变、书法字体、手绘边框、硬偏移阴影） |
| @font-face Latin 覆盖 | ✅ 完成 | 英文文本用 sans-serif，中文用 Ma Shan Zheng |
| 流式输出 | ✅ 完成 | SSE streaming + typing cursor，严格遵守 SSE v1 三阶段生命周期 (start→delta→done) + 15s 心跳 |
| Markdown 渲染 | ✅ 完成 | 代码块紧凑布局 + 复制图标浮动右上角 + 语言标签内联 + 字体统一 Ma Shan Zheng |
| Header 标题 | ✅ 完成 | 对称三区布局，标题可点击唤起宠物，新建会话右侧按钮 |
| 工具面板 | ✅ 完成 | 定位限制在手机框架内，不再超出操作界面 |
| 错误处理 | ✅ 完成 | 中文友好提示 + 去重 + 429 自动重试 |
| 消息气泡 | ✅ 完成 | user/assistant/error 三种样式，用户气泡 min-width: 120px，推理与结果拆分独立卡片 |
| 历史记录 | ✅ 完成 | 卡片式布局 + 搜索 |
| 欢迎页选项 | ✅ 完成 | 4 分类 × 4 选项，全部可用，工具链完整 |
| SuggestionPills | ✅ 完成 | 仅会话中展示快捷操作，欢迎页隐藏 |
| 手机框架尺寸 | ✅ 完成 | 390px × 100dvh，与原型一致 |
| 抽屉定位 | ✅ 完成 | 工具/宠物/认证抽屉均限制在手机框架内 |
| 新建会话 | ✅ 完成 | 会话中 Header 右侧按钮，清空消息 + 恢复欢迎页 |
| 工具抽屉 | ✅ 完成 | 微信风格上拉抽屉，3 个媒体操作（相册/拍摄/文件），已清空原有快捷指令 |
| 宠物抽屉 | ✅ 完成 | 头像+心情+活动+想法 |
| 建议药丸 | ✅ 完成 | 水平滚动 |
| TraceCard | ✅ 完成 | 推理线程折叠卡片 + image/video/widget 内容块渲染 |
| Image Content Block | ✅ 完成 | 后端 image content block 发射 + streaming Markdown 去重 + 前端专用图片块渲染 + 会话重载恢复 |
| StreamingMessage | ✅ 完成 | typing dots + cursor blink |
| SuggestionPills | ✅ 完成 | 水平滚动建议 |
| H5ChatInput | ✅ 完成 | 输入框 + shadow-card + 图片预览缩略图 + 附件显示 |

## 后端 API

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| `/chat/stream` | POST | ✅ | SSE 流式响应 + 15s 心跳 + message.error + 规范错误码 (E00001-E00011) + 多模态 content 字段 (§9.1) |
| `/models` | GET | ✅ | 7 个可选模型 |
| `/sessions` | GET | ✅ | 历史会话列表 |
| `/personas` | GET | ✅ | 4 个专家角色 |
| `/capabilities` | GET | ✅ | 可用技能 + 工具 |
| `/connectors` | GET | ✅ | amap + tavily |
| `/knowledge` | GET | ✅ | 知识文档 |
