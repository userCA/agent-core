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

---

## 功能缺口（未修复）

| 功能 | 优先级 | 说明 |
|---|---|---|
| Provider 自动重试 | P0 | 429/500/502/503 自动重试 + exponential backoff |
| Token 计数 | P1 | 当前 `total_tokens()` 是简单求和，需按模型 tokenizer 估算 |
| Compaction 自动触发 | P1 | AgentSession 在 `AgentEnd` 时调用 `_maybe_compact`，但策略简单 |
| MCP Tool 适配 | P1 | `pyproject.toml` 已有 `mcp` extras，但无实现 |
| MongoDB Store | P2 | `pyproject.toml` 已有 `motor` extras，但无实现 |
| Session 树导航 | P3 | design.md 列为 v1 外 |
| HTML/JSONL 导出 | P3 | JSONL store 已有，但无专门 export API |

---

## 设计债务（未修复）

1. **`_default_convert_to_llm` 硬编码 OpenAI 格式**：`tool_calls` / `tool` role 是 OpenAI 特有的
2. **`AgentLoopConfig` 类型过宽**：`tool_registry`、`before_tool_call` 类型为 `Any`
3. **`AgentContext` 与 `AgentState` 的消息类型不一致**：运行时都应是 `AgentMessage`，可考虑泛型约束
4. **`time.time()` 精度**：消息时间戳用 float，但 `datetime.now(timezone.utc).isoformat()` 更利于持久化
