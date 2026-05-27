# agent-core 开发日志

> 按天拆分为子文档，防止问题重复出现、改错原有功能。
> 每天一个文件，索引页只保留摘要和跳转。

---

## 索引

| 日期 | 解决的问题 | 文件 |
|---|---|---|
| 2026-05-13 | 1. `loop.py` system_prompt bug  2. 接入日志系统  3. Skill 加载系统  4. 本地工具  5. scene 聊天助手  6. Minimax API 验证 | [2026-05-13.md](development-log/2026-05-13.md) |
| 2026-05-14 | 7. CLI `.env` 加载修复  8. CLI 错误可见性  9. CLI 四优化  10. Skill 调用验证  11. CLI 输出规范化  12. SSE Chat 前端重构  13. HTTP 400 + think 闪现修复 | [2026-05-14.md](development-log/2026-05-14.md) |
| 2026-05-15 | 14. Turn 级 Human-in-the-Loop 机制（工具暂停 → 前端卡片输入 → loop 恢复） | [2026-05-15.md](development-log/2026-05-15.md) |
| 2026-05-18 | 18. agent-core 架构优化：工具可插拔性、资源发现加载、系统提示词构建 | [2026-05-18.md](development-log/2026-05-18.md) |
| 2026-05-22 | 19. Memory & Retrieval 基础子系统：Protocol + 内存适配器 + Extension/Tool 桥接  20. AIGC 视频生成工具 + HTTP/SSE 请求级鉴权透传 | [2026-05-22.md](development-log/2026-05-22.md) |
| 2026-05-26 | 22. 架构审查与全面优化  23. Core 目录冗余清理 + 开发流程 Skill  24. 设计债务清偿（P0-P3） | [2026-05-26.md](development-log/2026-05-26.md) |
| 2026-05-27 | 25. loop.py 清理  26. dead code 删除  27. message_converter 提取  28. 前端交互优化（thinking dots/步骤展开/流式思考）  29. 测试质量修复  30. CLAUDE.md 中文化 | [2026-05-27.md](development-log/2026-05-27.md) |

---

## 功能缺口

### 已解决（2026-05-26 优化）

| 功能 | 原优先级 | 解决方案 |
|---|---|---|
| Provider 自动重试 | P0 | `loop.py` 重试循环 + exponential backoff + jitter，支持 retryable/overflow 两种重试路径 |
| Extension Hook 正式 API | P0 | `Agent.add_*_hook()` 公共方法 + 链式串接 + sync/async 自动检测 |
| Compaction 自动触发 | P1 | overflow 检测 → `compact_callback` → 自动重试，`AgentSession` 注入回调 |
| MCP Tool 适配 | P1 | `tools/mcp_tool.py`：`MCPConnection` + `MCPToolAdapter` + `discover_mcp_tools()` |
| OpenTelemetry 可观测性 | P2 | `observability.py`：`observe()` context manager + `trace_llm_call()` |
| `AgentLoopConfig` 类型过宽 | 设计债 | 全部 `Any` 字段替换为精确类型别名 |
| 消息格式 OpenAI 硬编码 | 设计债 | Anthropic provider 提供 native converter，Agent 自动选择 |

### 仍未解决

| 功能 | 优先级 | 说明 |
|---|---|---|
| Token 计数 | P1 | 当前 `total_tokens()` 是简单求和，需按模型 tokenizer 估算 |
| MongoDB Store | P2 | `pyproject.toml` 已有 `motor` extras，但无实现 |
| Session 树导航 | P3 | design.md 列为 v1 外 |
| HTML/JSONL 导出 | P3 | JSONL store 已有，但无专门 export API |
| `AgentContext` 与 `AgentState` 消息类型不一致 | 设计债 | 运行时都应是 `AgentMessage`，可考虑泛型约束 |
| `time.time()` 精度 | 设计债 | 消息时间戳用 float，`datetime.now(timezone.utc).isoformat()` 更利于持久化 |
