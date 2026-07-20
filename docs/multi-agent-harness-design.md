# Multi-Agent Harness 扩展方案

> 基于 pi-mono agent 框架的 harness 层，新增多 agent 编排能力。
> 
> 设计目标：编排器模式 + harness 扩展层 + 可配置隔离 + 专家路由

---

## 一、当前架构分析

### 1.1 AgentHarness 核心特征

`AgentHarness`（`packages/agent/src/harness/agent-harness.ts`）是一个**单 agent 运行时**：

- **Phase 状态机**：`idle → turn/compaction/branch_summary → idle`，同一时刻只能有一个 agent 在运行（busy 锁）
- **单一 Session**：每个 harness 绑定一个 Session，维护一棵会话树（session tree）
- **单一 Model**：通过 `setModel()` 切换，同一时刻只有一个模型在工作
- **Hook 系统**：`before_agent_start`、`tool_call`、`tool_result`、`context` 等，支持拦截和修改
- **Event 系统**：`subscribe()` 全局监听，`on()` 按类型监听

### 1.2 可用于构建多 Agent 的基础设施

| 机制 | 说明 |
|---|---|
| `AgentTool` | 允许将任何逻辑封装为 tool，包括启动另一个 agent |
| Event System | 完整的事件流（tool_call、tool_result、message_end 等），可用于跨 agent 协调 |
| Hook 拦截 | `beforeToolCall` / `afterToolCall` 可拦截和修改 tool 调用 |
| Steering / FollowUp | `steer()` / `followUp()` / `nextTurn()` 允许运行时注入消息 |
| Session Fork | `SessionRepo.fork()` 支持从现有会话分叉出新会话 |
| Custom Entry | `appendCustomEntry()` 支持存储自定义数据 |

### 1.3 现有 Subagent 实现（进程级隔离）

`packages/coding-agent/examples/extensions/subagent/index.ts` 展示了进程隔离式方案：

- 通过 `spawn("pi", [...])` 启动独立子进程
- JSON 模式 stdout 通信
- 支持 Single / Parallel / Chain 三种模式
- `mapWithConcurrencyLimit()` 控制并发

**局限**：进程创建开销、IPC 序列化、无法共享内存中的 Session/Models 状态。

---

## 二、核心架构决策

### "Harness-in-Tool" 组合模式

编排器本身是一个标准 `AgentHarness` 实例，通过一个特殊的 `delegate_task` AgentTool 将 sub-agent 委派能力注入。每个 sub-agent 也是独立的 `AgentHarness` 实例，进程内运行，共享 `ExecutionEnv` 和 `Models`，但 Session 可配置隔离级别。

**与现有 subagent extension 的关键区别**：
- 现有方案：进程级隔离（spawn 新 pi 进程），IPC JSON 通信
- 本方案：进程内隔离（in-process AgentHarness），直接引用共享，零序列化开销

### 架构总览

```
MultiAgentHarness (工厂函数创建)
├── orchestrator: AgentHarness          ← 标准 AgentHarness，持有 delegate_task 工具
│   ├── delegate_task tool              ← AgentTool，通过闭包捕获 registry + runner
│   └── systemPrompt + routingPrompt    ← 包含可用 agent 列表描述
├── AgentProfileRegistry                ← 专家 agent 注册表 + 路由提示词生成
└── SubAgentRunner                      ← 管理 sub-agent 生命周期 + 并发控制
    └── SubAgentFactory                 ← 根据 profile 创建 AgentHarness（含 Session 隔离策略）
```

---

## 三、实现步骤

### Step 1: 新增 Multi-Agent 类型定义

**新建文件**: `packages/agent/src/harness/multi-agent/types.ts`

```typescript
// 隔离模式
type IsolationMode = "isolated" | "forked";
// isolated: 独立 Session，完全独立上下文
// forked: 通过 SessionRepo.fork() 继承父 session 历史快照

// 专家 agent 配置
interface AgentProfile {
  name: string;
  description: string;                    // LLM 可见的专长描述
  systemPrompt: string | ((ctx) => string | Promise<string>);
  model?: Model<any>;                     // 可覆盖默认模型
  thinkingLevel?: ThinkingLevel;
  tools?: string[];                       // 可用工具名白名单（从编排器工具池中过滤）
  isolation?: IsolationMode;              // 默认 "isolated"
  maxConcurrency?: number;               // 该 profile 最大并行实例，默认 1
}

// 编排器配置
interface MultiAgentHarnessOptions {
  profiles: AgentProfile[];
  maxConcurrentAgents?: number;           // 全局并发上限，默认 4
  delegateToolName?: string;              // 默认 "delegate_task"
  routingPrompt?: string;                 // 额外路由指导
}

// sub-agent 执行结果
interface SubAgentResult {
  agentName: string;
  task: string;
  status: "completed" | "failed" | "aborted";
  response: AssistantMessage;
  usage: { input: number; output: number; cost: number };
  durationMs: number;
  errorMessage?: string;
}

// 委派模式（与现有 subagent extension 一致）
type DelegationMode = "single" | "parallel" | "chain";
```

### Step 2: 实现 AgentProfileRegistry（专家路由注册表）

**新建文件**: `packages/agent/src/harness/multi-agent/agent-profile-registry.ts`

```typescript
class AgentProfileRegistry {
  private profiles = new Map<string, AgentProfile>();

  register(profile: AgentProfile): void;
  unregister(name: string): void;
  resolve(name: string): AgentProfile | undefined;
  list(): AgentProfile[];

  // 生成系统提示词中的 agent 列表（XML 格式，参考 formatSkillsForSystemPrompt）
  formatForSystemPrompt(): string;
  // 输出类似:
  // <available_agents>
  //   <agent><name>code-reviewer</name><description>...</description></agent>
  // </available_agents>
}
```

参考 `formatSkillsForSystemPrompt`（`packages/agent/src/harness/system-prompt.ts`）的 XML 格式化模式。

### Step 3: AgentHarness 新增两个公开 getter

**修改文件**: `packages/agent/src/harness/agent-harness.ts`（约 6 行增量）

在 `getModel()` (行 829) 附近新增：

```typescript
getPhase(): AgentHarnessPhase {
    return this.phase;
}

getSession(): Session {
    return this.session;
}
```

**风险评估**: 纯增量 getter，零回归风险。

### Step 4: 实现 SubAgentFactory（sub-agent 创建工厂）

**新建文件**: `packages/agent/src/harness/multi-agent/sub-agent-factory.ts`

```typescript
class SubAgentFactory {
  constructor(
    private env: ExecutionEnv,
    private models: Models,
    private sessionRepo: SessionRepo,
    private streamOptions: AgentHarnessStreamOptions,
    private allTools: AgentTool[],        // 编排器的完整工具池
  ) {}

  async create(
    profile: AgentProfile,
    options: { parentSession?: Session },
  ): Promise<AgentHarness> {
    // 1. Session 隔离策略
    let session: Session;
    if (profile.isolation === "forked" && options.parentSession) {
      const metadata = await options.parentSession.getMetadata();
      session = await this.sessionRepo.fork(metadata, {});
    } else {
      session = await this.sessionRepo.create({});
    }

    // 2. 工具过滤（profile.tools 白名单与 allTools 交集）
    const tools = profile.tools
      ? this.allTools.filter(t => profile.tools!.includes(t.name))
      : this.allTools;

    // 3. 创建标准 AgentHarness
    return new AgentHarness({
      env: this.env,
      session,
      models: this.models,
      tools,
      systemPrompt: profile.systemPrompt,
      model: profile.model ?? /* default model */,
      thinkingLevel: profile.thinkingLevel ?? "off",
      streamOptions: this.streamOptions,
    });
  }
}
```

复用 `SessionRepo.fork()` 和 `SessionRepo.create()` 现有能力。

### Step 5: 实现 SubAgentRunner（执行器 + 并发控制）

**新建文件**: `packages/agent/src/harness/multi-agent/sub-agent-runner.ts`

```typescript
class SubAgentRunner {
  private factory: SubAgentFactory;
  private activeAgents = new Map<string, AgentHarness>();
  private semaphore: Semaphore;            // 全局并发限制

  async runSingle(
    profile: AgentProfile,
    task: string,
    options: { parentSession?: Session; signal?: AbortSignal },
  ): Promise<SubAgentResult> {
    // 1. 获取信号量
    // 2. factory.create(profile, options)
    // 3. subHarness.prompt(task)
    // 4. 收集结果，构建 SubAgentResult
    // 5. finally: 释放信号量，清理 activeAgents
  }

  async runParallel(
    tasks: Array<{ profile: AgentProfile; task: string }>,
    options: { parentSession?: Session; signal?: AbortSignal },
  ): Promise<SubAgentResult[]> {
    // 参考现有 mapWithConcurrencyLimit (subagent/index.ts L219-237)
  }

  async runChain(
    tasks: Array<{ profile: AgentProfile; task: string }>,
    options: { parentSession?: Session; signal?: AbortSignal },
  ): Promise<SubAgentResult[]> {
    // 顺序执行，将上一个结果注入下一个 task（{previous} 占位符）
  }

  async abortAll(): Promise<void> {
    // 遍历 activeAgents 调用 abort()
  }
}
```

### Step 6: 实现 delegate_task 工具 + createMultiAgentHarness 工厂函数

**新建文件**: `packages/agent/src/harness/multi-agent/factory.ts`

这是整个方案的核心组装点：

```typescript
function createMultiAgentHarness(
  config: MultiAgentHarnessOptions,
  baseOptions: Omit<AgentHarnessOptions, "tools" | "systemPrompt"> & { tools?: AgentTool[] },
): AgentHarness {
  // 1. 创建 AgentProfileRegistry，注册所有 profiles
  const registry = new AgentProfileRegistry();
  for (const p of config.profiles) registry.register(p);

  // 2. 创建 SubAgentFactory
  const factory = new SubAgentFactory(baseOptions.env, baseOptions.models, ...);

  // 3. 创建 SubAgentRunner
  const runner = new SubAgentRunner(factory, config.maxConcurrentAgents ?? 4);

  // 4. 创建 delegate_task 工具（核心枢纽）
  const delegateTool: AgentTool = {
    name: config.delegateToolName ?? "delegate_task",
    label: "Delegate Task",
    description: `Delegate tasks to specialized sub-agents. ${registry.formatForSystemPrompt()}`,
    parameters: Type.Object({
      mode: Type.Optional(StringEnum(["single", "parallel", "chain"])),
      agent: Type.Optional(Type.String()),
      task: Type.Optional(Type.String()),
      tasks: Type.Optional(Type.Array(Type.Object({
        agent: Type.String(),
        task: Type.String(),
      }))),
    }),
    execute: async (toolCallId, params, signal, onUpdate) => {
      // 根据 mode 调用 runner.runSingle/runParallel/runChain
      // 通过 onUpdate 报告进度
      // 返回 SubAgentResult 作为 tool result
    },
  };

  // 5. 构建编排器系统提示（包含路由指导）
  const orchestratorSystemPrompt = buildOrchestratorPrompt(registry, config.routingPrompt);

  // 6. 组合工具列表 = 用户工具 + delegate_task
  const tools = [...(baseOptions.tools ?? []), delegateTool];

  // 7. 创建并返回标准 AgentHarness
  return new AgentHarness({
    ...baseOptions,
    tools,
    systemPrompt: orchestratorSystemPrompt,
  });
}
```

**关键设计**: `delegate_task` 通过闭包捕获 `registry` 和 `runner` 引用，无需修改 AgentTool 接口。编排器 LLM 通过工具描述中的 agent 列表自主决定路由。

### Step 7: 导出和包配置

**修改文件**: `packages/agent/src/index.ts`

新增导出：
```typescript
// Multi-agent
export * from "./harness/multi-agent/types.ts";
export * from "./harness/multi-agent/agent-profile-registry.ts";
export * from "./harness/multi-agent/sub-agent-factory.ts";
export * from "./harness/multi-agent/sub-agent-runner.ts";
export * from "./harness/multi-agent/factory.ts";
```

### Step 8: 测试

**新建文件**: `packages/agent/test/harness/multi-agent/`

| 测试文件 | 覆盖场景 |
|---------|---------|
| `agent-profile-registry.test.ts` | 注册/注销/查找/formatForSystemPrompt |
| `sub-agent-factory.test.ts` | isolated 创建、forked 创建、工具过滤 |
| `sub-agent-runner.test.ts` | 单执行、并行执行、链式执行、并发限制、abort 传播 |
| `factory.test.ts` | createMultiAgentHarness 集成测试：编排器 prompt → delegate_task → sub-agent 完成 |

---

## 四、步骤依赖关系

```
Step 1 (类型) ─┬── Step 2 (Registry) ──┐
               ├── Step 3 (getter) ────┤
               └── Step 4 (Factory) ───┤
                                       │
                   Step 5 (Runner) ◀───┤
                       │               │
                   Step 6 (工具+工厂) ◀┘
                       │
                   Step 7 (导出)
                       │
                   Step 8 (测试)
```

**推荐实施顺序**: 1 → 2 + 3（并行）→ 4 → 5 → 6 → 7 → 8

**预计代码量**: 新增约 600-700 行（不含测试），修改现有代码约 11 行。

---

## 五、风险与缓解

| 风险 | 级别 | 缓解 |
|------|------|------|
| 嵌套 LLM 延迟（编排器 + sub-agent 两层调用） | 中 | 编排器可用轻量模型；delegate_task 的 onUpdate 实时报告进度 |
| AbortController 传播到 sub-agent | 中 | runner 使用 AbortSignal.any() 链接父子 signal；abortAll() 兜底 |
| forked 模式 Session 内存膨胀 | 低 | 默认推荐 isolated；forked 仅用于需要历史上下文的场景 |
| delegate_task 与用户工具名冲突 | 低 | delegateToolName 可配置 |
| 编排器 phase 锁（turn 中执行 tool） | 无 | sub-agent 使用独立 Session，通过 AgentToolResult 返回结果，自然隔离 |

---

## 六、被拒绝的替代方案

| 方案 | 拒绝原因 |
|------|---------|
| **继承 AgentHarness 创建 MultiAgentHarness 子类** | 破坏现有类型契约，泛型参数组合复杂，且 phase 状态机需要重写 |
| **shared_session 模式（多 agent 共享同一 Session）** | Session 写入并发安全风险高，需要引入分布式锁，收益不明显 |
| **TaskDecomposer DAG 任务分解器** | 首版引入 LLM DAG 分解过于复杂，可由编排器 LLM 自行规划；后续可作为增强 |
| **AgentPool 池化管理** | 首版 sub-agent 按需创建/销毁即可，池化是性能优化，过早引入增加复杂度 |
| **进程级隔离（spawn 模式）** | 已有 coding-agent subagent extension 实现，本方案提供进程内替代，性能更优 |

---

## 七、关键参考文件

| 文件 | 作用 |
|------|------|
| `packages/agent/src/harness/agent-harness.ts` | AgentHarness 核心类，理解 prompt/executeTurn/hook 流程 |
| `packages/agent/src/harness/types.ts` | 类型定义，AgentHarnessOptions/AgentHarnessEvent 等 |
| `packages/agent/src/harness/session/session.ts` | Session 管理，buildContext 扩展点 |
| `packages/agent/src/harness/session/repo-utils.ts` | getEntriesToFork() — Session 隔离的技术基础 |
| `packages/agent/src/agent-loop.ts` | Agent Loop 纯函数，理解 tool 执行和 hook 调用时序 |
| `packages/coding-agent/examples/extensions/subagent/index.ts` | 现有进程级 sub-agent 参考实现 |
| `packages/agent/src/harness/system-prompt.ts` | formatSkillsForSystemPrompt — XML 格式化参考 |
