# Skill 严格渐进式暴露改造方案

> **日期：** 2026-08-12  
> **状态：** 待实施（指导后续开发的权威方案）  
> **范围：** `agent_core` skill 加载语义 + scene 组装 + OTEL/事件观测；**不**改 Langfuse SDK 绑定策略  
> **关联：**  
> - `docs/superpowers/specs/2026-08-11-langfuse-scene-integration-design.md`  
> - `docs/skill-self-evolution.md` / `docs/skill-evolution-gap-and-roadmap.md`  
> - `agent_core/prompts/builder.py`、`agent_core/resources/skills.py`、`agent_core/observability.py`  
> - `scene/h5/chat_assistant.py`、`scene/http_sse/chat_assistant.py`  
> **For agentic workers：** 实施时配合 `superpowers:subagent-driven-development` 或 `executing-plans`，按文末「实施任务」逐项勾选。

---

## 0. 一句话目标

**宿主可预加载 Skill 元数据与正文缓存；发给模型的上下文默认只有目录（name+description）；全文必须经显式激活进入对话，并产出可观测的激活事件。**

成功后：Langfuse / 日志能回答「本 run 激活了哪些 skill」，且**不再依赖不可靠的 tool→skill 一对一映射作为主归因**。

---

## 1. 背景与问题

### 1.1 现状

| 层 | 当前行为 |
|----|----------|
| 宿主初始化 | `ResourceLoader.load_skills()` 已把 `SKILL.md` 解析进内存（含全文） |
| 模型 system prompt | 仅注入 `<available_skills>` 的 **name + description**（半渐进） |
| 全文进入对话 | 主要靠 `/skill:name` 宿主注入；**无强制**「先 load 再执行」 |
| Skill 观测 | `SkillStart` 多由「关联 tool 被调用」推断；`SkillTraceCollector` 用 `dict[tool]=skill` |
| OTEL（Langfuse） | 仅有 `agent.run` / `agent.turn` / `agent.llm_call` / `agent.tool_call.*`，**无 skill span/属性** |

### 1.2 核心矛盾

1. **工具可追踪、skill 难追踪**：tool 有 `execute` 边界；skill 是 prompt/策略包，无强制激活门闩。  
2. **tool→skill 映射不准**：同一 tool（如 `bash`/`read`）可被多个 skill 使用；`dict[tool]=skill` 后写覆盖先写，不能当主真相。  
3. **半渐进不够**：目录已在 prompt，模型可仅凭 description「脑补」执行，观测上无法区分「见过目录」与「真正加载正文」。

### 1.3 决策（已锁定）

采用 **对模型上下文的严格渐进式暴露**；**保留**宿主启动时 `load_skills()` 缓存。

| 决策 | 选择 | 不选 |
|------|------|------|
| D1 暴露语义 | 未激活 skill 全文不得进入发给模型的 messages/system | 启动时把全部 SKILL.md 塞进 system |
| D2 宿主加载 | 启动解析 + 内存缓存 | 每次激活都强制重新读盘（可选校验 mtime，非必须） |
| D3 激活通道 | **专用 `load_skill` 工具** + **保留 `/skill:`**（等价激活） | 仅靠通用 `read`/`bash` 无约定 |
| D4 主归因 | 激活事实（inject / load_skill / 受控读） | tool→skill 一对一反推 |
| D5 观测 | `SkillStart`/`SkillEnd` + OTEL attributes（阶段 A）+ 可选 `agent.skill.*` span（阶段 B） | 只改 evolution collector、不上报观测面 |
| D6 tool→skill | 降为弱信号：`candidates_by_tool` 多值列表或删除主路径 | 继续作为唯一归因 |

---

## 2. 目标与非目标

### 2.1 目标

1. **严格语义**：默认上下文只有 skill 目录；全文仅在激活后进入。  
2. **显式激活**：`load_skill` 与 `/skill:` 产生同一套激活事件与观测字段。  
3. **可观测**：按 `run_id` / `session_id` 能列出 `skills.activated`、来源（`injected` | `load_skill` | `path_read`）。  
4. **可演进**：为 skill evolution 提供干净激活信号，弱化错误映射。  
5. **可开关**：用环境变量/配置渐进 rollout，避免一次切死存量行为。

### 2.2 非目标

- 不把 skill 改成独立子进程/子 Agent runtime。  
- 不强制删除 `/skill:`。  
- 不在 `agent_core/core` 引入 `langfuse` 包。  
- 不做「是否遵守 skill 规则」的合规评测（那是 judge/evolution，不是激活追踪）。  
- 不要求前端大改 UI（可用文案提示「先 load_skill」；设置页可选后续再做）。

---

## 3. 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│  Host（ChatAssistant / ResourceLoader）                       │
│  load_skills() → 内存 Skill 目录 + 正文缓存（启动一次）         │
└────────────────────────────┬────────────────────────────────┘
                             │
         system prompt 仅 L1 │  <available_skills> name+desc
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Model context                                                │
│  未激活：只有目录                                              │
│  激活后：注入 <skill name="..." location="...">正文</skill>   │
└────────────────────────────┬────────────────────────────────┘
                             │
        激活通道（任一即可）   │
        ├─ /skill:name        → 宿主 inject（已有，对齐事件）
        ├─ load_skill 工具    → 模型按需拉取（新增，主路径）
        └─ 受控 path read     → 可选：读 **/skills/**/SKILL.md 视同激活
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  观测                                                         │
│  AgentEvent: SkillStart / SkillEnd                            │
│  OTEL: agent.run/turn attributes + 可选 agent.skill.{name}    │
│  Evolution: 以 activated set 为主，不再依赖一对一 tool 映射     │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 三层内容（与 Claude Agent Skills 对齐）

| 层 | 内容 | 何时进模型上下文 | 观测 |
|----|------|------------------|------|
| L1 目录 | name + description | 始终（可经 skill_routing 过滤） | `skills.available` |
| L2 正文 | SKILL.md body | 仅激活后 | `skills.activated` + `SkillStart` |
| L3 附件 | references/scripts/assets | 模型再 read/bash（普通工具 span） | 可选 path 启发式 |

### 3.2 「使用 skill」的定义（验收用语）

本方案中 **「使用了 skill X」** 仅当满足：

> 本 run（或本 session，见配置）内发生过对 X 的 **显式激活**（`/skill:` / `load_skill` / 受控 SKILL.md 读取），并因此产生 `SkillStart(skill_name=X)`。

模型仅看到 L1 description 就自行发挥，**不算**已使用（可另打 `skills.mentioned_only` 指标，非必须）。

---

## 4. 激活 API 设计

### 4.1 新增工具：`load_skill`

**建议位置：** `agent_core/tools/load_skill.py`（或 `agent_core/skills/load_skill_tool.py`），在 scene `ChatAssistant.create` 注册进 `ToolRegistry`。

**定义草案：**

```python
ToolDefinition(
    name="load_skill",
    description=(
        "Load the full instructions for a skill by name before following it. "
        "Call this when an available skill matches the user task. "
        "Do not claim to follow a skill you have not loaded."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Exact skill name from <available_skills>",
            },
        },
        "required": ["name"],
    },
)
```

**执行语义：**

1. 在已加载的 `skills` 列表中按 `name` 查找；不存在 → `ToolResult(is_error=True, text="unknown skill")`。  
2. 若 `disable_model_invocation=True` 且非用户 `/skill:` 路径 → 拒绝模型侧 load（与现有 frontmatter 语义一致）。  
3. 成功则返回与 `/skill:` 相同结构的文本块（便于模型与观测统一）：

```text
<skill name="{name}" location="{origin}">
References are relative to {base_dir}.

{body without frontmatter}
</skill>
```

4. **副作用（必须）：** 发出 `SkillStart`；把 `name` 记入 session/run 的 `activated_skills`；写 OTEL 属性/span。  
5. **幂等：** 同一 run 内重复 load 同一 skill → 可返回正文，但 `SkillStart` 不重复刷屏（第二次可跳过事件或打 `skills.reload=true`）。

### 4.2 保留并对齐：`/skill:name`

现有 `ChatAssistant` 展开逻辑保留。改造点：

- 注入成功后 **必须** `SkillStart`（不要等关联 tool 才发）。  
- `source=injected`。  
- 与 `load_skill` 共用同一 `activate_skill(name, source=...)` 辅助函数。

### 4.3 可选：受控 path read

**阶段 C（可选）**：在 `read`/`bash` 的 after-hook 中，若路径匹配 skill 根下的 `SKILL.md`，调用同一 `activate_skill(..., source=path_read)`。

**阶段 A/B 可不做**，避免与普通文件读取纠缠；文档中注明为增强项。

### 4.4 System prompt 指引（必改文案）

在 skills section 追加简短规则（中英择一，与现有 prompt 风格一致），例如：

```text
Skills are listed below by name and description only.
Before following a skill's procedure, you MUST call load_skill with that name
(or the user may invoke /skill:<name>). Do not invent skill steps from the description alone.
```

`SystemPromptBuilder`（`agent_core/prompts/builder.py`）在组装 `<available_skills>` 时写入。

### 4.5 Skill routing 兼容

`skill_routing=True` 时仍只过滤 L1 目录；**不**自动注入全文。路由结果写入观测：`skills.routed=[...]`（available 子集）。

---

## 5. 观测方案

### 5.1 AgentEvent（已有类型，改触发时机）

| 事件 | 何时发 | 字段 |
|------|--------|------|
| `SkillStart` | 激活成功时（inject / load_skill / 可选 path_read） | `skill_name`, `skill_description`；建议扩展 `source`（若改事件模型成本高，可先放 metadata / 并行日志） |
| `SkillEnd` | TurnEnd / AgentEnd 时对已激活集合收尾（保持现有 H5 行为） | `skill_name` |

**禁止：** 仅因「某共享 tool 被调用」就发 `SkillStart`（删除或降级该路径）。

### 5.2 OTEL / Langfuse（对齐现有 `observability.py`）

**阶段 A（最小可用，优先做）：**

在 `agent.run` 与/或 `agent.turn` span 上设置：

```text
agent.skills.available   = ["a","b",...]      # 可选，体积大时可只放 count
agent.skills.activated   = ["a"]
agent.skills.activation_source.a = "load_skill" | "injected" | "path_read"
```

或扁平：

```text
agent.skills.activated = "a,b"
agent.skills.sources   = "a:load_skill,b:injected"
```

**阶段 B（树更清晰）：**

```text
agent.run
 └─ agent.turn
     ├─ agent.skill.{name}          # SkillStart→SkillEnd 或 load_skill 工具生命周期
     │    └─ agent.tool_call.*      # 可选：仅文档约定，不强绑父子（异步 hook 下父子难保证时以 attributes 为准）
     ├─ agent.llm_call
     └─ agent.tool_call.load_skill
```

原则：**attributes 是主筛选手段；span 是增强。** 父子绑不稳时不要阻塞阶段 A 验收。

### 5.3 SkillTraceCollector 改造

文件：`agent_core/skill_evolution/collector.py`

| 改动 | 说明 |
|------|------|
| 主归因 | `_turn_active_skills` 仅由 `SkillStart` / 注入解析填充 |
| tool 映射 | `_tool_to_skill: dict[str, str]` → `_tool_to_skills: dict[str, list[str]]` 或删除自动 `_activate_skill` |
| 弱信号 | 若保留，写入 `execution_details["tool_skill_candidates"]`，**不**单独激活 |
| 单 available 回退 | 可保留（保守），但文档标明为弱启发式 |

Scene 侧删除或停止写入一对一 `_tool_to_skill` 持久化映射作为真相源（`chat_assistant.py` 中 mapping persist 逻辑一并审视）。

---

## 6. 配置与开关

| 变量 / 配置 | 默认 | 含义 |
|-------------|------|------|
| `AGENT_SKILL_PROGRESSIVE=1` | 建议新默认 `1`（若担心回归可先 `0`） | 启用严格语义 + prompt 指引 + load_skill 注册 |
| `AGENT_SKILL_PATH_READ_ACTIVATION=0` | `0` | 读 SKILL.md 是否视同激活（阶段 C） |
| `AGENT_SKILL_LEGACY_TOOL_MAP=0` | `0` | 为 `1` 时短暂保留旧 tool→skill 激活（迁移期） |

Scene lifespan / `ChatAssistant.create` 读取上述环境变量。

---

## 7. 文件改动地图

| 文件 | 职责 |
|------|------|
| **Create** `agent_core/tools/load_skill.py` | `LoadSkillTool` 实现 |
| **Modify** `agent_core/prompts/builder.py` | L1 目录 + 渐进式使用说明 |
| **Modify** `agent_core/observability.py` | run/turn 写入 skills attributes；可选 skill span helper |
| **Modify** `agent_core/skill_evolution/collector.py` | 归因改为激活优先；弱化 tool 映射 |
| **Modify** `agent_core/core/events.py` | 可选：`SkillStart.source` 字段 |
| **Modify** `scene/h5/chat_assistant.py` | 注册工具；`/skill:` 立即 SkillStart；共用 activate；去一对一 tool 激活 |
| **Modify** `scene/http_sse/chat_assistant.py` | 同上（与 H5 对齐） |
| **Modify** `scene/cli/chat_assistant.py` | 至少对齐 `/skill:` 与 load_skill（若 CLI 暴露工具） |
| **Create** `tests/tools/test_load_skill.py` | 工具行为 |
| **Create/Modify** `tests/core/test_observability.py` | skills attributes |
| **Create/Modify** `tests/skill_evolution/test_collector_attribution.py` | 归因单测 |
| **Modify** `docs/FEATURES.md` | 功能状态 |
| **Modify** `docs/development-log/YYYY-MM-DD.md` | 提交前日志（收尾时） |

**不要编辑：** `demo/`（只读参考）。

---

## 8. 实施任务（可勾选）

> 建议顺序：A → B → C。每阶段可独立合并。TDD：先测后码。

### 阶段 A — 激活边界 + 事件真相（必须）

#### Task A1: `load_skill` 工具

**Files:** Create `agent_core/tools/load_skill.py`；Test `tests/tools/test_load_skill.py`

- [ ] 写失败单测：未知 skill → is_error  
- [ ] 写成功单测：返回 `<skill name=...>` 块且无 frontmatter  
- [ ] 写单测：`disable_model_invocation` 拒绝模型 load  
- [ ] 实现 `LoadSkillTool`（依赖注入：`skills: list[Skill]` + `on_activate: Callable`）  
- [ ] 跑通 `pytest tests/tools/test_load_skill.py`

#### Task A2: 统一 `activate_skill`

**Files:** 建议抽到 `agent_core/skills/activation.py`（或 scene 内 helper 若想先薄）；两端 chat_assistant 调用

- [ ] API：`activate_skill(name, *, source, emit_skill_start=...)`  
- [ ] `/skill:` 展开成功后调用，`source="injected"`  
- [ ] `load_skill` 成功后调用，`source="load_skill"`  
- [ ] 同一 run 幂等：第二次不重复 `SkillStart`（或带 reload 标记）  
- [ ] **删除**「ToolExecutionStart + `_tool_to_skill` → SkillStart」主路径（或闸到 `AGENT_SKILL_LEGACY_TOOL_MAP`）

#### Task A3: Prompt 指引 + 注册工具

**Files:** `agent_core/prompts/builder.py`；`scene/h5/chat_assistant.py`；`scene/http_sse/chat_assistant.py`

- [ ] builder 增加渐进式使用说明  
- [ ] `AGENT_SKILL_PROGRESSIVE=1` 时注册 `load_skill`  
- [ ] 确认 system prompt 仍只含 L1，不含全文  
- [ ] 单测或快照：prompt 含 `load_skill` 指引且 skills section 无大段 body

#### Task A4: Collector 归因修正

**Files:** `agent_core/skill_evolution/collector.py` + tests

- [ ] 默认不因 tool 名激活 skill  
- [ ] `SkillStart` / 注入块仍激活  
- [ ] 多 skill 共享 tool 时不错误唯一归因  
- [ ] `pytest tests/skill_evolution/ -k attribution`（按实际测试名）

**阶段 A 验收：**

1. 新会话不发 `/skill:`、不调 `load_skill` → 无 `SkillStart`，prompt 无 skill 全文。  
2. `/skill:foo` 或模型 `load_skill(foo)` → 有 `SkillStart`，消息/工具结果含全文。  
3. 调用共享 tool 不会单独制造 skill 激活。

---

### 阶段 B — OTEL / Langfuse 可见（强烈建议紧接 A）

#### Task B1: run/turn attributes

**Files:** `agent_core/observability.py`；`tests/core/test_observability.py`；harness/observe 接线处传入 activated 列表

- [ ] `observe()` 或 turn 结束时写入 `agent.skills.activated` 等属性  
- [ ] 单测：假 tracer 断言 attributes  
- [ ] 本地联调：Langfuse 打开 `agent.run` 能看到 activated skill 名

#### Task B2:（可选）`agent.skill.*` span

- [ ] `trace_skill(name, source=...)` context manager  
- [ ] 在 activate / SkillEnd 边界 start/end  
- [ ] 文档说明与 tool span 的关系；不强求 tool 成为 skill 子 span

**阶段 B 验收：**

一次「load_skill → 再调业务 tool」的对话后，Langfuse 中同 `run_id` 可见 activated skill；工具 span 仍独立存在。

---

### 阶段 C — 增强（可选）

- [ ] `AGENT_SKILL_PATH_READ_ACTIVATION=1`：受控路径读 `SKILL.md` → activate  
- [ ] H5 SkillsPage 文案：说明须 `load_skill` 或 `/skill:`  
- [ ] 清理遗留 `_tool_to_skill` 持久化与 FEATURES「SkillStart planned」状态  
- [ ] 更新 `docs/FEATURES.md`、development-log

---

## 9. 测试矩阵

| 场景 | 期望 |
|------|------|
| 冷启动只聊天、不 load | 无 SkillStart；无 skill 全文在 messages |
| `/skill:x` | SkillStart；正文注入；OTEL activated 含 x |
| 模型 `load_skill(x)` | 同上，source=load_skill |
| 重复 load 同一 skill | 正文可返回；SkillStart 不刷屏 |
| 未知 skill 名 | tool error；无激活 |
| `disable-model-invocation` | 模型 load 失败；用户 `/skill:` 仍可（若产品允许） |
| 两 skill 均列 `bash` | 调 bash **不**激活任一 skill |
| skill_routing 过滤 | 仅子集出现在 available；不自动全文 |
| `AGENT_SKILL_PROGRESSIVE=0` | 行为接近改造前（迁移安全阀） |

---

## 10. 迁移与风险

| 风险 | 缓解 |
|------|------|
| 模型不调 `load_skill` 直接瞎做 | prompt 强约束 + 评测抽检；必要时后续加「未激活则降权」策略（非本方案必须） |
| 多一轮才 load，延迟 +1 tool turn | 可接受；可用 `/skill:` 用户侧预激活 |
| H5/http_sse/cli 三端不一致 | 清单强制三处 chat_assistant 对齐；共享 `activation` 模块 |
| evolution 历史数据变少 | 预期内（去掉假阳性）；文档注明归因口径变更日 |
| prompt 变长（指引文案） | 控制在十余行内 |

**回滚：** `AGENT_SKILL_PROGRESSIVE=0` + 临时 `AGENT_SKILL_LEGACY_TOOL_MAP=1`。

---

## 11. 明确不做 / 反模式

1. **不要**用「最后一个调用的 tool 属于哪个 skill」当主观测。  
2. **不要**在 system prompt 预置全部 SKILL.md 正文。  
3. **不要**为了面板好看把用户隐私全文默认打进 Langfuse（沿用 `LANGFUSE_CAPTURE_CONTENT` 策略；skill 名与 source 默认足够）。  
4. **不要**编辑 `demo/`。  
5. **不要**把 Langfuse SDK 塞进 `agent_core/core`。

---

## 12. 验收清单（发布前）

- [ ] 单元测试：load_skill、activation 幂等、collector 归因、observability attributes  
- [ ] H5 手工：`/skill:某技能` → 前端可见 skill 步骤（若 UI 已订阅 SkillStart）且 Langfuse 有 activated  
- [ ] H5 手工：自然语言触发 → 模型先 `load_skill` 再干活（抽检）  
- [ ] 共享工具调用不会单独产生 SkillStart  
- [ ] `FEATURES.md` 与 development-log 已更新  
- [ ] 开关关闭时无崩溃、行为可回退  

---

## 13. 建议排期

| 阶段 | 预估 | 产出 |
|------|------|------|
| A | 1–2 日 | 语义正确 + 事件可信 |
| B | 0.5–1 日 | Langfuse 可筛选 skill |
| C | 按需 | path 激活 + 文案/清理 |

---

## 14. 给实施者的起步命令

```bash
# 可编辑安装
pip install -e ".[test]"

# 相关测试（随任务增加路径）
pytest tests/tools/test_load_skill.py -v
pytest tests/core/test_observability.py -v
pytest tests/skill_evolution/ -v

# 本地 H5（验证激活与 Langfuse）
PORT=8001 python -m scene.h5.server
# 另开：cd scene/h5/static && npm run dev
```

实施时以本文 **§1.3 决策** 与 **§8 任务列表** 为准；若与口头讨论冲突，以本文为准并更新本文「状态 / 决策」节。
