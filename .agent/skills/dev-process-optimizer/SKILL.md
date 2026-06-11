---
name: dev-process-optimizer
description: "通用架构开发流程优化 — 涉及跨层协议/架构决策时加载。后端详情见 dev-process-backend，前端详情见 dev-process-frontend。"
---

# 开发流程优化（总入口）

对本项目的跨层变更或架构决策，先过这篇。纯后端/纯前端问题直接加载对应子 skill。

---

## 架构速查

### 分层依赖
```
scene/（CLI / HTTP SSE / Voice WS）     ← 最外层
  ├─→ session/（AgentSession 组合层）
  │     ├─→ extensions/（Hook / 扩展）
  │     └─→ compaction/（上下文压缩）
  └─→ core/（纯运行时，零 IO）           ← 最内层
        ├─→ tools/（工具抽象）
        └─→ providers/（LLM 适配）
```

依赖方向由外向内。`core/` 不 import `session/` 或 `scene/`。共享类型下沉到 `core/context.py`（如 `AgentLoopConfig`）。

### 数据流全链路
```
User Input → Agent.prompt() → agent_loop()
  → convert_to_llm(messages) → [transform_context] → provider.stream()
    → StreamEvent → AgentEvent → subscribe listeners
      → Tool 执行（parallel / sequential）
        → ToolResult → context.messages + state.messages
          → 下一轮 或 drain steering/follow-up 队列 → 再一轮 或 break
```

每加一个数据通道，从消费者倒推验证每层格式兼容。注意 steering/follow-up 队列在每轮结束后 drain，有内容则继续循环。

### 关键原则

1. **Protocol 优先**：存储/LLM/工具来源先定义 Protocol，再附内置实现。`ModelProvider`、`SessionStore`、`Tool` 都是 Protocol。
2. **显式事件**：Agent loop 产出 discriminated union 的 `AgentEvent`，消费者通过 `agent.subscribe(listener)` 订阅。不靠扫描列表判断状态。
3. **数据/显示分离**：后端 `convert_to_llm` 是数据转换（送 LLM），`ToolResult.display` 是显示提示（送 UI）。前端 `currentText` 是数据源（原始），`getDisplayableText` 是显示过滤（渲染层）。两者不能混用。
4. **转换在 Adapter**：provider 负责消息格式转换，格式映射不进 core/loop.py。Anthropic 产 Anthropic-native 格式，OpenAI 产 OpenAI 格式。
5. **删干净**：不保留兼容层/fallback/deprecated。一处定义，一处维护。

---

## 子 Skill 索引

**后端问题** → 加载 `dev-process-backend`
- 模块间去重（一处定义，一处维护）
- 类型安全（消灭 `getattr`，dataclass 直接访问）
- Hook 链式调用（sync/async 兼容、元数据合并）
- 流式重试（缓冲事件，只在最终 attempt 发射）
- Tool 结果双向同步（context + state）
- API 迁移全量消费者检查
- 错误处理（先日志再存储）
- 死代码检测（同时检查写路径和读路径）
- 配置链路端到端追踪

**前端问题** → 加载 `dev-process-frontend`
- 数据源/显示源分离
- 中间状态同步风险
- 四场景回归测试矩阵
- 边缘问题性价比评估
- 代码替换边界安全
- 流式数据流唯一真相源
- Zustand store 职责分离
- 打字机队列不可预过滤

---

## 使用方式

```
1. 这是跨层/架构问题？→ 读本文 + 对应子 skill
2. 纯后端（core/ providers/ session/ tools/）？→ dev-process-backend
3. 纯前端（scene/http_sse/static/src/）？→ dev-process-frontend
4. 不确定？→ 先读本文，再按涉及的文件判断
```

处理完成后：在对应子 skill 中追加新发现的反模式/规则。跨层规则追加到本文。

---

## 内容维护规则

**目的：保持 skill 精炼，防止退化成一堆过时/重复/无关的条目。**

### 新增规则的三问

新增一条规则之前，必须三个都是"是"：

1. **真重复过？** — 同一个错误至少出现过两次，或者一次但后果是灾难性的（数据丢失、全线崩溃）
2. **能说清怎么办？** — 规则必须包含具体的检测方法或操作步骤，不能只有"注意 X"这种模糊提醒
3. **现在还有用？** — 涉及的代码/模块还存在。已删除的模块、已废弃的方案，对应的规则也应该删除

三问不通过 → 不添加。

### 合并优先

新案例能归入已有规则时，**追加案例到已有规则**，不新建规则：

```
已有规则：类型安全 —— 消灭 getattr
新案例：  发现 getattr(config, "timeout", 30) 
操作：    追加到已有规则，不新建 "配置超时规则"
```

### 删除检查

每次新增规则后，快速扫一遍现有规则：
- 有没有规则现在看起来意思一样？→ 合并
- 有没有规则覆盖的代码/模块已经删了？→ 删除
- 有没有规则超过半年没被触发过？→ 考虑删除

### 条数上限

保持每个子 skill ≤ 15 条规则。超过时，合并最相似的、删除最过时的，腾出空间再新增。
