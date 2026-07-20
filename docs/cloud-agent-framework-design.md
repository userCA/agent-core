# 云 Agent 框架设计文档

## 1. 概述

本文档描述了一个基于现有 `pi-agent-core` + `coding-agent` 架构衍生的云原生 Agent 框架，适配多租户、高并发部署场景。

**目标**：保留当前框架的架构优势（事件驱动设计、工具注册表、Skill 注入、扩展系统、系统提示词构建），同时去除单用户、单会话、本地文件系统的假设。

**范围**：本设计面向通用云 Agent（API 服务、自动化平台、多用户聊天系统），不涉及代码审查或本地 IDE 集成。

---

## 2. 术语表

| 术语 | 定义 |
|------|------|
| **对话（Conversation）** | 单个用户与 Agent 的对话线程。等价于当前框架中的一个 `AgentSession` 实例。 |
| **轮次（Turn）** | 对话中一次完整的提问-回复周期，可能包含工具调用。 |
| **共享服务（Shared Service）** | 初始化后为只读或线程安全的单例服务。在所有对话间共享。 |
| **对话服务（Conversation Service）** | 为单个对话线程管理可变状态的实例。 |
| **Skill** | 带有 frontmatter 的 Markdown 文件，包含特定任务的专项指令。 |
| **扩展（Extension）** | 注册自定义工具、命令和事件处理器的插件模块。 |
| **工具（Tool）** | LLM 可通过 JSON Schema 调用的函数。 |
| **上下文压缩（Context Compaction）** | 当对话历史接近模型上下文窗口限制时，对历史消息进行摘要压缩。 |
| **知识库（Knowledge Base）** | 外部文档集合，通过 RAG（检索增强生成）为对话提供领域知识。 |
| **检索器（Retriever）** | 根据查询从知识库中检索相关文档片段的组件。 |

---

## 3. 当前框架分析

### 3.1 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│  应用层（模式：interactive, print, rpc）                    │
│  - TUI 渲染、快捷键、CLI 参数                               │
├─────────────────────────────────────────────────────────────┤
│  会话管理层                                                 │
│  - AgentSessionRuntime（会话生命周期：新建/切换/分叉）      │
│  - AgentSession（事件循环、工具注册表、上下文压缩）          │
├─────────────────────────────────────────────────────────────┤
│  核心 Agent 层（@mariozechner/pi-agent-core）               │
│  - Agent（LLM 循环：prompt/stream/tool_call/steer）         │
│  - 可变状态：messages, tools, systemPrompt, model            │
├─────────────────────────────────────────────────────────────┤
│  基础设施层                                                 │
│  - SessionManager（本地 JSONL 文件）                        │
│  - SettingsManager（本地 JSON 配置）                        │
│  - ResourceLoader（本地文件系统扫描）                       │
│  - ModelRegistry（API Key 管理）                            │
│  - AuthStorage（本地凭证文件）                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 当前事件流

```
用户输入
    |
    v
[AgentSession.prompt()] -> Skill 展开 -> 模板展开
    |
    v
[Agent.prompt()] -> LLM API 调用
    |
    v
[Agent 发出事件] -> agent_start, turn_start, message_start, ...
    |
    v
[AgentSession._handleAgentEvent()] -> 串行队列处理
    |
    v
[ExtensionRunner.emit()] -> 扩展钩子
    |
    v
[SessionManager.appendMessage()] -> 本地文件追加
    |
    v
[AgentSession._emit()] -> 外部监听器（TUI）
```

### 3.3 值得保留的优势

| 优势 | 重要性 |
|------|--------|
| **事件驱动架构** | 核心逻辑与表现层解耦 |
| **工具注册表与定义** | LLM 接收结构化 Schema；工具是一等公民 |
| **Skill 注入** | `formatSkillsForPrompt()` 将 Skill 描述注入系统提示词 |
| **系统提示词构建器** | `buildSystemPrompt()` 从工具、指南、上下文文件、Skill 组合提示词 |
| **扩展生命周期钩子** | `before_agent_start`, `tool_call`, `tool_result`, `context` 支持深度定制 |
| **自动重试** | 对速率限制和瞬态错误进行指数退避 |
| **上下文压缩** | 当上下文接近模型限制时自动摘要 |
| **Steer/FollowUp 队列** | 允许 Agent 仍在处理时用户发送消息 |

### 3.4 云部署的局限性

| 局限性 | 根本原因 | 影响 |
|--------|---------|------|
| 单会话设计 | `AgentSession` 管理一个对话的可变状态 | 无法同时处理多个用户 |
| 串行事件队列 | `_agentEventQueue: Promise<void>` 链式处理所有事件 | 对话内外均无并行性 |
| 本地文件存储 | `SessionManager` 使用 `appendFileSync` 写 JSONL | 无多节点支持；无事务安全 |
| 全局可变状态 | `_steeringMessages`, `_retryAttempt`, `_compactionAbortController` | 实例共享会导致状态泄漏 |
| 单 Agent 实例 | `Agent.state` 是可变的且共享的 | 不同用户的消息会交错 |
| 同步 I/O | `readFileSync`, `appendFileSync`, `writeFileSync` | 高负载下阻塞事件循环 |
| 本地凭证存储 | `AuthStorage` 从 `~/.pi/agent/auth.json` 读取 | 不适用于密钥管理服务 |
| TUI 耦合扩展 | `ExtensionUIContext` 包含 `select`, `confirm`, `setFooter` | 云 Agent 没有终端 UI |
| 无外部知识库 | 当前框架无 RAG 扩展口 | 无法接入企业知识库 |

---

## 4. 设计目标

### 4.1 功能目标

1. **多租户**：支持跨不同用户/租户的数千个并发对话
2. **水平扩展**：可水平扩展的无状态对话 Worker，部署在负载均衡器后
3. **实时事件**：事件通过 WebSocket 或 Server-Sent Events 流向客户端
4. **工具生态**：支持按租户、按对话或全局自定义工具
5. **Skill 管理**：从远程存储（S3、数据库、Git）加载 Skill，支持热重载
6. **可插拔持久化**：通过配置支持有状态（持久化历史）和无状态（纯内存）两种对话模式
7. **RAG 知识库**：支持接入外部知识库，通过检索增强生成提升回答质量

### 4.2 双运行模式

框架支持两种运行模式，可通过配置按对话或全局设置：

| 模式 | 持久化 | 适用场景 | 资源成本 |
|------|--------|---------|---------|
| **有状态** | 消息保存到外部存储（PostgreSQL/Redis） | 多轮对话、断线重连、历史浏览 | 较高（DB I/O + 存储） |
| **无状态** | 纯内存，不持久化 | 一次性任务、临时聊天、高吞吐场景 | 极低（仅内存） |

**核心设计原则**：核心 Agent 循环（prompt、stream、工具执行、事件发射）在两种模式下完全一致。只有持久化层不同。有状态模式增加 `ConversationStore` + `MessageStore`；无状态模式完全省略它们。

### 4.3 非功能目标

| 目标 | 指标 |
|------|------|
| 吞吐量 | 每个 Worker 实例 100+ 并发对话（无状态），50+（有状态） |
| 延迟 | P95 < 500ms（不含 LLM 延迟） |
| 可用性 | 99.9% 正常运行时间，优雅降级 |
| 隔离性 | 对话状态完全隔离；无共享可变状态 |
| 可观测性 | 结构化日志、分布式追踪、每对话指标 |

### 4.4 约束

- 保留事件驱动、基于订阅的交互模型
- 保留工具注册表 + Skill 注入模式
- 保持与现有扩展钩子类型的兼容性
- 避免修改 `pi-agent-core` 中的 `Agent` 类（作为依赖处理）
- 持久化层必须可插拔，不修改核心 Agent 逻辑

---

## 5. 整体架构

### 5.1 高层架构图

```
                              客户端
                          (Web/移动/API)
                                |
                    ┌───────────┴───────────┐
                    |     负载均衡器        |
                    └───────────┬───────────┘
                                |
            ┌───────────────────┼───────────────────┐
            |                   |                   |
    ┌───────▼───────┐   ┌───────▼───────┐   ┌───────▼───────┐
    |  Worker Pod 1 |   |  Worker Pod 2 |   |  Worker Pod N |
    |               |   |               |   |               |
    | ┌───────────┐ |   | ┌───────────┐ |   | ┌───────────┐ |
    | | API 网关  | |   | | API 网关  | |   | | API 网关  | |
    | | (WS/SSE)  | |   | | (WS/SSE)  | |   | | (WS/SSE)  | |
    | └─────┬─────┘ |   | └─────┬─────┘ |   | └─────┬─────┘ |
    |       |       |   |       |       |   |       |       |
    | ┌─────▼─────┐ |   | ┌─────▼─────┐ |   | ┌─────▼─────┐ |
    | | 对话工厂  | |   | | 对话工厂  | |   | | 对话工厂  | |
    | └─────┬─────┘ |   | └─────┬─────┘ |   | └─────┬─────┘ |
    |       |       |   |       |       |   |       |       |
    |  ┌────┴────┐  |   |  ┌────┴────┐  |   |  ┌────┴────┐  |
    |  | 对话 A  |  |   |  | 对话 C  |  |   |  | 对话 E  |  |
    |  | 对话 B  |  |   |  | 对话 D  |  |   |  | 对话 F  |  |
    |  └─────────┘  |   |  └─────────┘  |   |  └─────────┘  |
    |       |       |   |       |       |   |       |       |
    |  ┌────┴────────┐ |   |  ┌────┴────────┐ |   |  ┌────┴────────┐ |
    |  |  共享服务   | |   |  |  共享服务   | |   |  |  共享服务   | |
    |  | ModelRegistry | |   |  | ModelRegistry | |   |  | ModelRegistry | |
    |  | SkillRegistry | |   |  | SkillRegistry | |   |  | SkillRegistry | |
    |  | ToolRegistry  | |   |  | ToolRegistry  | |   |  | ToolRegistry  | |
    |  | KnowledgeBase | |   |  | KnowledgeBase | |   |  | KnowledgeBase | |
    |  └─────────────┘ |   |  └─────────────┘ |   |  └─────────────┘ |
    └───────────────┘   └───────────────┘   └───────────────┘
                                |
                    ┌───────────┴───────────┐
                    |     共享存储层        |
                    |  ┌───────┐ ┌────────┐ |
                    |  | Redis | |PostgreSQL| |
                    |  |(事件/ | | (会话/  | |
                    |  |缓存)  | | 知识库) | |
                    |  └───────┘ └────────┘ |
                    |  ┌──────────────────┐ |
                    |  |   对象存储       | |
                    |  | (Skill/Prompt/   | |
                    |  |  知识库文档)     | |
                    |  └──────────────────┘ |
                    └───────────────────────┘
```

### 5.2 组件分类

| 层级 | 组件 | 作用域 | 可变性 | 存储 | 模式 |
|------|------|--------|--------|------|------|
| 网关 | API 网关 | 每 Worker 单例 | 可变（连接状态） | 内存 | 两者 |
| 对话 | ConversationEngine | 每对话 | 可变 | 仅内存 | 两者 |
| 对话 | Agent (pi-agent-core) | 每对话 | 可变 | 仅内存 | 两者 |
| 对话 | ConversationStore | 每对话 | 可变 | PostgreSQL/Redis | 仅状态 |
| 对话 | MessageStore | 每对话 | 可变 | PostgreSQL/Redis | 仅状态 |
| 共享 | ModelRegistry | 单例 | 大部分只读 | 内存缓存 | 两者 |
| 共享 | SkillRegistry | 单例 | 大部分只读 | 内存缓存 + S3 | 两者 |
| 共享 | ToolRegistry | 单例 | 大部分只读 | 内存缓存 | 两者 |
| 共享 | **KnowledgeBaseRegistry** | 单例 | 大部分只读 | 向量数据库 + 对象存储 | 两者 |
| 共享 | ConfigProvider | 单例 | 大部分只读 | 环境变量 + DB | 两者 |
| 共享 | EventBus | 单例 | 可变 | 内存 + Redis pub/sub | 两者 |

---

## 6. 核心组件设计

### 6.1 ConversationEngine（替换 AgentSession）

`ConversationEngine` 是主要的每对话编排器。它替换 `AgentSession`，但保留其事件循环、工具注册、重试逻辑和上下文压缩行为。

```typescript
type PersistenceMode = "stateful" | "stateless";

interface ConversationEngineConfig {
  conversationId: string;
  userId: string;
  tenantId?: string;

  // 核心依赖（每对话）
  agent: Agent;

  // 共享依赖（单例）
  modelRegistry: ModelRegistry;
  skillRegistry: SkillRegistry;
  toolRegistry: ToolRegistry;
  knowledgeBaseRegistry: KnowledgeBaseRegistry;  // RAG 知识库注册表
  configProvider: ConfigProvider;
  eventBus: EventBus;

  // 持久化模式
  persistenceMode: PersistenceMode;

  // 存储适配器（persistenceMode === "stateful" 时必需）
  conversationStore?: ConversationStore;
  messageStore?: MessageStore;

  // 可选
  customTools?: ToolDefinition[];
  initialSystemPrompt?: string;
  maxContextTokens?: number;
}

class ConversationEngine {
  private agent: Agent;
  private conversationId: string;
  private userId: string;
  private persistenceMode: PersistenceMode;

  // 每对话可变状态（隔离）
  private eventListeners: ConversationEventListener[] = [];
  private agentEventQueue: Promise<void> = Promise.resolve();
  private steeringMessages: QueuedMessage[] = [];
  private followUpMessages: QueuedMessage[] = [];
  private pendingNextTurnMessages: CustomMessage[] = [];
  private retryState: RetryState | null = null;
  private compactionState: CompactionState | null = null;
  private toolRegistry: Map<string, AgentTool> = new Map();
  private toolDefinitions: Map<string, ToolDefinitionEntry> = new Map();

  // 共享服务（注入，初始化后只读）
  private sharedModelRegistry: ModelRegistry;
  private sharedSkillRegistry: SkillRegistry;
  private sharedToolRegistry: ToolRegistry;
  private sharedKnowledgeBaseRegistry: KnowledgeBaseRegistry;

  // 可选存储（仅状态模式使用）
  private conversationStore?: ConversationStore;
  private messageStore?: MessageStore;

  constructor(config: ConversationEngineConfig) { ... }

  // 主 API
  async prompt(text: string, options?: PromptOptions): Promise<void>;
  async steer(text: string, images?: ImageContent[]): Promise<void>;
  async followUp(text: string, images?: ImageContent[]): Promise<void>;
  async abort(): Promise<void>;

  // 事件订阅
  subscribe(listener: ConversationEventListener): () => void;

  // 工具管理
  setActiveTools(toolNames: string[]): void;
  getActiveToolNames(): string[];
  registerCustomTool(tool: ToolDefinition): void;

  // 状态
  getContextUsage(): ContextUsage | undefined;
  getStats(): ConversationStats;

  // 生命周期
  dispose(): void;
}
```

#### 关键设计决策

1. **每对话一个 `Agent` 实例**：`pi-agent-core` 的 `Agent` 类具有可变状态（`agent.state.messages`, `agent.state.tools`）。每对话创建一个 `Agent` 是唯一安全的方法。

2. **事件队列按对话隔离**：串行的 `_agentEventQueue` 保留，但限定在单个对话内。这保持了顺序保证，不会阻塞其他对话。

3. **无全局可变状态**：`AgentSession` 中的所有全局状态（`_steeringMessages`, `_retryAttempt`, `_compactionAbortController`）现在都按实例隔离。

4. **可插拔持久化**：存储适配器是可选的。在 `stateless` 模式下，所有对话状态存在于 `agent.state.messages`（仅内存）。在 `stateful` 模式下，消息还会持久化到外部存储以支持恢复和历史查询。

### 6.2 ConversationFactory

创建和管理 `ConversationEngine` 实例。处理连接路由、会话恢复和清理。

```typescript
interface ConversationFactoryConfig {
  sharedServices: SharedServices;
  maxConversationsPerWorker: number;
  idleTimeoutMs: number;
  defaultTools?: ToolDefinition[];
}

class ConversationFactory {
  private conversations: Map<string, ConversationEngine> = new Map();
  private sharedServices: SharedServices;
  private maxConversations: number;

  async createOrResume(
    conversationId: string,
    userId: string,
    options?: ResumeOptions,
  ): Promise<ConversationEngine>;

  async get(conversationId: string): Promise<ConversationEngine | undefined>;

  async close(conversationId: string): Promise<void>;

  async closeIdleConversations(): Promise<void>;

  getMetrics(): FactoryMetrics;
}
```

### 6.3 共享服务

每 Worker 实例化一次、在所有对话间共享的服务。

```typescript
interface SharedServices {
  modelRegistry: ModelRegistry;
  skillRegistry: SkillRegistry;
  toolRegistry: ToolRegistry;
  knowledgeBaseRegistry: KnowledgeBaseRegistry;  // RAG 知识库
  configProvider: ConfigProvider;
  eventBus: EventBus;
  metricsCollector: MetricsCollector;
}
```

#### 6.3.1 ModelRegistry

**当前**：`AuthStorage` + `ModelRegistry` 从本地 JSON 文件读取 API Key。

**云适配**：
- API Key 来自环境变量、密钥管理服务（AWS Secrets Manager、HashiCorp Vault）或租户特定配置
- 模型定义在启动时加载并缓存到内存
- 运行时无凭证文件 I/O

```typescript
interface CloudModelRegistry {
  // 初始化：从配置加载模型定义
  initialize(modelDefinitions: ModelDefinition[]): void;

  // 获取租户可用模型
  getAvailableModels(tenantId?: string): Model[];

  // 解析模型的 API 凭证
  getCredentials(model: Model, tenantId?: string): Promise<CredentialsResult>;

  // 按 provider + id 查找模型
  find(provider: string, modelId: string): Model | undefined;
}
```

#### 6.3.2 SkillRegistry

**当前**：`ResourceLoader` + `loadSkills()` 扫描本地文件系统目录。

**云适配**：
- Skill 从对象存储（S3、GCS、MinIO）或数据库在启动时加载
- 内存缓存，支持基于 TTL 的刷新
- 支持通过 Webhook 或轮询热重载

```typescript
interface SkillRegistry {
  // 启动时加载所有 Skill
  initialize(source: SkillSource): Promise<void>;

  // 获取租户可见的 Skill（按租户配置过滤）
  getSkills(tenantId?: string): Skill[];

  // 格式化 Skill 以注入系统提示词
  formatSkillsForPrompt(skills: Skill[]): string;

  // 热重载（定期调用或通过 Webhook）
  reload(): Promise<void>;
}

type SkillSource =
  | { type: "s3"; bucket: string; prefix: string }
  | { type: "database"; connectionString: string }
  | { type: "git"; url: string; branch: string }
  | { type: "filesystem"; paths: string[] }; // 用于本地开发
```

#### 6.3.3 ToolRegistry

**当前**：工具通过 `createAllToolDefinitions()` 按 cwd 创建。

**云适配**：
- 工具定义在启动时或按租户注册
- 工具**实现**由应用层提供
- 工具 Schema 被缓存并复用

```typescript
interface ToolRegistry {
  // 注册全局工具
  registerGlobalTools(tools: ToolDefinition[]): void;

  // 注册租户特定工具
  registerTenantTools(tenantId: string, tools: ToolDefinition[]): void;

  // 获取对话生效工具
  getToolsForConversation(
    conversationId: string,
    tenantId?: string,
    customTools?: ToolDefinition[],
  ): ToolDefinition[];

  // 按名称获取工具实现
  getToolImplementation(name: string): AgentTool | undefined;
}
```

#### 6.3.4 ConfigProvider

将 `SettingsManager` 替换为适合云部署的配置系统。

```typescript
interface ConfigProvider {
  // 获取全局配置
  getGlobalConfig<T>(key: string, defaultValue: T): T;

  // 获取租户特定配置
  getTenantConfig<T>(tenantId: string, key: string, defaultValue: T): T;

  // 获取对话特定配置
  getConversationConfig<T>(conversationId: string, key: string, defaultValue: T): T;

  // 重试行为配置
  getRetryConfig(): RetryConfig;

  // 上下文压缩配置
  getCompactionConfig(): CompactionConfig;

  // 思考级别配置
  getThinkingConfig(): ThinkingConfig;
}
```

### 6.4 存储适配器（可选）

存储适配器**仅在状态模式下需要**。在无状态模式下，所有对话状态存在于 `agent.state.messages`，对话结束或 Worker 重启时销毁。

#### 6.4.1 无状态模式：纯内存

在无状态模式下，`ConversationEngine` 不使用任何外部存储。权威数据源是 `agent.state.messages`。

```typescript
// 无状态模式：不需要存储
const engine = new ConversationEngine({
  conversationId: "conv-123",
  userId: "user-456",
  agent: new Agent({ ... }),
  persistenceMode: "stateless",
  // conversationStore 和 messageStore 省略
});
```

**无状态模式下的上下文压缩**：直接操作 `agent.state.messages`：

```typescript
// 直接内存压缩
private compactMessages(messages: AgentMessage[], summary: string): AgentMessage[] {
  const compactionMessage: AgentMessage = {
    role: "system",
    content: `Previous conversation summary: ${summary}`,
  };
  // 保留最近消息，用摘要替换较早消息
  const recentMessages = messages.slice(-this.keepRecentCount);
  return [compactionMessage, ...recentMessages];
}
```

#### 6.4.2 有状态模式：持久化存储

在有状态模式下，`ConversationStore` 和 `MessageStore` 适配器提供持久化。支持：
- Worker 重启后恢复对话
- 通过 API 浏览历史
- 跨设备会话连续性

```typescript
interface ConversationStore {
  create(conversation: ConversationRecord): Promise<void>;
  get(conversationId: string): Promise<ConversationRecord | null>;
  update(conversationId: string, updates: Partial<ConversationRecord>): Promise<void>;
  listByUser(userId: string, options?: ListOptions): Promise<ConversationRecord[]>;
  delete(conversationId: string): Promise<void>;
}

interface MessageStore {
  appendMessage(conversationId: string, message: ConversationMessage): Promise<string>;
  appendEvent(conversationId: string, event: ConversationEvent): Promise<string>;
  getMessages(
    conversationId: string,
    options?: { after?: Date; limit?: number; before?: Date },
  ): Promise<ConversationMessage[]>;
  getMessageHistory(conversationId: string): Promise<ConversationMessage[]>;
  getEvents(conversationId: string): Promise<ConversationEvent[]>;
  markCompacted(conversationId: string, upToMessageId: string, summary: string): Promise<void>;
}
```

**有状态模式初始化**：

```typescript
const engine = new ConversationEngine({
  conversationId: "conv-123",
  userId: "user-456",
  agent: new Agent({ ... }),
  persistenceMode: "stateful",
  conversationStore: new PostgresConversationStore(dbPool),
  messageStore: new PostgresMessageStore(dbPool),
});
```

#### 6.4.3 存储实现矩阵

| 存储后端 | ConversationStore | MessageStore | 适用场景 |
|---------|-------------------|--------------|---------|
| **PostgreSQL** | 完整 CRUD + 列表 | 完整历史 + 分页 | 主持久化存储 |
| **Redis** | TTL 元数据 | 序列化消息数组 | 快速恢复，短会话 |
| **S3 + DynamoDB** | DynamoDB 元数据 | 每对话一个 S3 对象 | 无服务器，超长会话 |
| **内存** | `MemoryConversationStore` | `MemoryMessageStore` | 测试，有状态模拟 |

#### 6.4.4 PostgreSQL Schema（有状态模式）

```sql
-- 对话表
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    tenant_id TEXT,
    title TEXT,
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    thinking_level TEXT NOT NULL DEFAULT 'off',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE INDEX idx_conversations_user ON conversations(user_id, updated_at DESC);
CREATE INDEX idx_conversations_tenant ON conversations(tenant_id, updated_at DESC);

-- 消息表
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES messages(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool', 'system', 'custom')),
    content TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text',
    metadata JSONB DEFAULT '{}',
    token_count INTEGER,
    cost_cents INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at DESC);

-- 事件表（模型变更、思考级别变更、压缩）
CREATE TABLE conversation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_conversation ON conversation_events(conversation_id, created_at DESC);

-- 压缩记录表
CREATE TABLE compactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    first_kept_message_id UUID NOT NULL REFERENCES messages(id),
    tokens_before INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 6.5 RAG 知识库服务（KnowledgeBaseRegistry）

RAG（检索增强生成）是云 Agent 框架的核心扩展能力。通过接入外部知识库，Agent 可以在回答时引用结构化文档、产品手册、FAQ、代码库等企业知识。

#### 6.5.1 RAG 架构定位

```
┌─────────────────────────────────────────────┐
│           KnowledgeBaseRegistry             │
│  （每 Worker 单例，所有对话共享）            │
├─────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐          │
│  │ Document    │  │  Document   │          │
│  │   Store     │  │   Indexer   │          │
│  │ (原始文档)  │  │ (解析/分块/ │          │
│  │             │  │  向量化)    │          │
│  └──────┬──────┘  └──────┬──────┘          │
│         │                │                  │
│         └────────────────┘                  │
│                      │                      │
│              ┌───────▼───────┐              │
│              │ Vector Store  │              │
│              │ (向量数据库)  │              │
│              └───────┬───────┘              │
│                      │                      │
│              ┌───────▼───────┐              │
│              │  Retriever    │              │
│              │ (语义检索)    │              │
│              └───────────────┘              │
└─────────────────────────────────────────────┘
                      │
              ┌───────▼───────┐
              │ ContextInjector │
              │ (注入对话上下文)│
              └───────────────┘
```

#### 6.5.2 核心接口

```typescript
interface KnowledgeBaseRegistry {
  // 注册知识库
  registerKnowledgeBase(kb: KnowledgeBaseConfig): Promise<void>;

  // 注销知识库
  unregisterKnowledgeBase(kbId: string): void;

  // 按租户获取知识库列表
  getKnowledgeBases(tenantId?: string): KnowledgeBase[];

  // 检索（核心接口）
  retrieve(query: RetrieveQuery): Promise<RetrieveResult>;

  // 批量索引文档
  indexDocuments(kbId: string, documents: Document[]): Promise<void>;

  // 删除文档
  deleteDocuments(kbId: string, docIds: string[]): Promise<void>;
}

interface KnowledgeBaseConfig {
  id: string;
  name: string;
  tenantId?: string;
  description?: string;
  // 向量存储配置
  vectorStore: VectorStoreConfig;
  // 检索参数
  retrievalConfig?: RetrievalConfig;
}

interface RetrieveQuery {
  query: string;
  knowledgeBaseIds?: string[];     // 限定检索范围
  tenantId?: string;
  topK?: number;                    // 默认 5
  similarityThreshold?: number;     // 相似度阈值，默认 0.7
  filters?: Record<string, unknown>; // 元数据过滤
}

interface RetrieveResult {
  chunks: DocumentChunk[];
  totalChunks: number;
  query: string;
}

interface DocumentChunk {
  id: string;
  content: string;
  sourceDocument: {
    id: string;
    title: string;
    url?: string;
  };
  metadata: Record<string, unknown>;
  similarity: number;
}
```

#### 6.5.3 文档索引流程

```typescript
interface DocumentIndexer {
  // 解析文档（支持 PDF、Word、Markdown、TXT、HTML 等）
  parse(document: RawDocument): Promise<ParsedDocument>;

  // 分块策略
  chunk(document: ParsedDocument, strategy: ChunkStrategy): DocumentChunk[];

  // 向量化
  embed(chunks: DocumentChunk[]): Promise<EmbeddedChunk[]>;

  // 写入向量存储
  store(kbId: string, chunks: EmbeddedChunk[]): Promise<void>;
}

interface ChunkStrategy {
  type: "fixed_size" | "semantic" | "recursive";
  chunkSize?: number;        // 默认 512 tokens
  chunkOverlap?: number;     // 默认 50 tokens
  separator?: string;        // 默认 "\n\n"
}
```

#### 6.5.4 向量存储适配

```typescript
interface VectorStoreAdapter {
  // 初始化集合/索引
  createCollection(name: string, dimension: number): Promise<void>;

  // 批量插入向量
  upsert(
    collection: string,
    vectors: Array<{
      id: string;
      vector: number[];
      metadata: Record<string, unknown>;
      content: string;
    }>,
  ): Promise<void>;

  // 相似度检索
  search(
    collection: string,
    queryVector: number[],
    options: { topK: number; filter?: Record<string, unknown> },
  ): Promise<SearchResult[]>;

  // 删除
  delete(collection: string, ids: string[]): Promise<void>;
}

// 支持的向量存储
interface VectorStoreConfig =
  | { type: "pgvector"; tableName: string; connectionString: string }
  | { type: "milvus"; collection: string; uri: string }
  | { type: "qdrant"; collection: string; url: string }
  | { type: "pinecone"; index: string; apiKey: string }
  | { type: "weaviate"; class: string; url: string }
  | { type: "redis"; indexName: string; redisUrl: string };
```

#### 6.5.5 pgvector Schema（推荐）

```sql
-- 知识库表
CREATE TABLE knowledge_bases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    tenant_id TEXT,
    description TEXT,
    embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
    embedding_dimension INTEGER NOT NULL DEFAULT 1536,
    chunk_size INTEGER NOT NULL DEFAULT 512,
    chunk_overlap INTEGER NOT NULL DEFAULT 50,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- 文档表
CREATE TABLE kb_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source_url TEXT,
    content_hash TEXT NOT NULL,
    doc_type TEXT NOT NULL CHECK (doc_type IN ('pdf', 'markdown', 'text', 'html', 'word', 'excel')),
    status TEXT NOT NULL DEFAULT 'indexed' CHECK (status IN ('pending', 'indexing', 'indexed', 'failed')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 文档片段表（含向量）
CREATE TABLE kb_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id UUID NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    kb_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    token_count INTEGER,
    metadata JSONB DEFAULT '{}',
    -- pgvector 向量列
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 向量相似度检索索引
CREATE INDEX idx_kb_chunks_embedding ON kb_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 全文检索索引（混合检索用）
CREATE INDEX idx_kb_chunks_fts ON kb_chunks USING gin (to_tsvector('chinese', content));

-- 按知识库查询索引
CREATE INDEX idx_kb_chunks_kb ON kb_chunks(kb_id);
```

#### 6.5.6 混合检索策略

```typescript
interface HybridRetriever {
  // 密集检索（语义相似度）
  denseRetrieve(query: string, options: RetrieveOptions): Promise<DocumentChunk[]>;

  // 稀疏检索（关键词匹配 / BM25）
  sparseRetrieve(query: string, options: RetrieveOptions): Promise<DocumentChunk[]>;

  // 混合检索（语义 + 关键词，RRF 融合）
  hybridRetrieve(query: string, options: RetrieveOptions): Promise<DocumentChunk[]>;
}

interface RetrieveOptions {
  kbId: string;
  topK?: number;
  alpha?: number;            // 混合权重，0=纯关键词, 1=纯语义
  rerank?: boolean;          // 是否重排序
  rerankModel?: string;      // 重排序模型
}
```

### 6.6 RAG 与对话系统的集成

RAG 不是独立模块，而是深度集成到对话流程中。以下是关键集成点：

#### 集成点 1：系统提示词构建时注入知识库描述

```typescript
// buildSystemPrompt 扩展
function buildSystemPromptWithKnowledgeBase(
  options: BuildSystemPromptOptions,
  kbRegistry: KnowledgeBaseRegistry,
): string {
  let prompt = buildSystemPrompt(options);

  // 注入可用知识库描述
  const knowledgeBases = kbRegistry.getKnowledgeBases(options.tenantId);
  if (knowledgeBases.length > 0) {
    prompt += "\n\n## 可用知识库\n\n";
    prompt += "以下知识库包含相关领域文档，可在回答时自动检索引用：\n\n";
    for (const kb of knowledgeBases) {
      prompt += `- ${kb.name}: ${kb.description}\n`;
    }
    prompt += "\n回答时会自动引用相关文档片段。引用格式：[来源: 文档标题]";
  }

  return prompt;
}
```

#### 集成点 2：`before_agent_start` 钩子中自动检索

```typescript
// 在 ConversationEngine.prompt() 中，发送给 LLM 前自动检索
async function injectRetrievedContext(
  conversationEngine: ConversationEngine,
  userQuery: string,
): Promise<void> {
  const kbRegistry = conversationEngine.sharedKnowledgeBaseRegistry;
  const knowledgeBases = kbRegistry.getKnowledgeBases(conversationEngine.tenantId);

  if (knowledgeBases.length === 0) return;

  // 自动检索相关知识
  const result = await kbRegistry.retrieve({
    query: userQuery,
    knowledgeBaseIds: knowledgeBases.map(kb => kb.id),
    tenantId: conversationEngine.tenantId,
    topK: 5,
  });

  if (result.chunks.length === 0) return;

  // 将检索结果作为上下文消息注入
  const contextMessage: CustomMessage = {
    role: "custom",
    customType: "retrieved_context",
    content: formatRetrievedChunks(result.chunks),
    display: false,  // 不显示给用户
  };

  conversationEngine.agent.state.messages.push(contextMessage);
}

function formatRetrievedChunks(chunks: DocumentChunk[]): string {
  const lines = ["以下是与用户问题相关的参考文档片段：\n"];
  for (const chunk of chunks) {
    lines.push(`[来源: ${chunk.sourceDocument.title}]`);
    lines.push(chunk.content);
    lines.push("");
  }
  return lines.join("\n");
}
```

#### 集成点 3：扩展 `context` 事件钩子

```typescript
// 扩展开发者可通过 context 钩子自定义检索逻辑
interface RAGExtension {
  onContext?(
    event: ContextEvent,
    context: CloudExtensionContext,
  ): Promise<ContextEventResult>;
}

// 示例：自定义检索扩展
const customRAGExtension: CloudExtension = {
  name: "custom-rag",
  async onContext(event, ctx) {
    const { knowledgeBaseRegistry } = ctx;

    // 获取最后一条用户消息作为查询
    const lastUserMessage = getLastUserMessage(event.messages);
    if (!lastUserMessage) return undefined;

    // 执行检索
    const result = await knowledgeBaseRegistry.retrieve({
      query: lastUserMessage,
      tenantId: ctx.tenantId,
      topK: 3,
    });

    if (result.chunks.length === 0) return undefined;

    // 将检索结果注入消息列表
    const ragMessage: AgentMessage = {
      role: "system",
      content: `参考信息：\n${result.chunks.map(c => c.content).join("\n---\n")}`,
    };

    return {
      messages: [...event.messages, ragMessage],
    };
  },
};
```

#### 集成点 4：工具层暴露检索工具

```typescript
// 将检索能力暴露为 LLM 可调用的工具
const searchKnowledgeBaseTool: ToolDefinition = {
  name: "search_knowledge_base",
  description: "从知识库中检索与用户问题相关的文档片段",
  parameters: {
    type: "object",
    properties: {
      query: {
        type: "string",
        description: "搜索查询",
      },
      knowledge_base: {
        type: "string",
        description: "知识库名称（可选，不指定则搜索所有）",
      },
      top_k: {
        type: "number",
        description: "返回结果数量",
        default: 5,
      },
    },
    required: ["query"],
  },
  async execute(args) {
    const result = await knowledgeBaseRegistry.retrieve({
      query: args.query,
      knowledgeBaseIds: args.knowledge_base ? [args.knowledge_base] : undefined,
      topK: args.top_k,
    });
    return {
      chunks: result.chunks.map(c => ({
        content: c.content,
        source: c.sourceDocument.title,
        similarity: c.similarity,
      })),
    };
  },
};
```

### 6.7 RAG 配置与多租户

```typescript
interface RAGConfig {
  // 全局默认配置
  defaultEmbeddingModel: string;      // "text-embedding-3-small"
  defaultEmbeddingDimension: number;  // 1536
  defaultChunkSize: number;           // 512
  defaultChunkOverlap: number;        // 50
  defaultTopK: number;                // 5
  defaultSimilarityThreshold: number; // 0.7

  // 每租户可覆盖
  getTenantRAGConfig(tenantId: string): TenantRAGConfig;
}

interface TenantRAGConfig {
  enabled: boolean;
  autoRetrieve: boolean;              // 是否在每轮自动检索
  knowledgeBaseIds: string[];         // 租户可访问的知识库
  maxChunksPerQuery: number;          // 每查询最大片段数
  injectPosition: "before_prompt" | "before_agent_start" | "as_tool";
  citationFormat: "inline" | "footnote" | "none";
}
```

---

## 7. 数据流

### 7.1 消息流

```
客户端 (WebSocket/SSE)
    |
    | POST /conversations/:id/messages
    v
API 网关
    |
    | 路由到持有对话的 Worker
    v
ConversationFactory.get(conversationId)
    |
    v
ConversationEngine.prompt(text, options)
    |
    |-- 1. 展开 Skill (/skill:name)
    |-- 2. 展开 Prompt 模板 (/template)
    |-- 3. 构建系统提示词（工具 + Skill + 指南）
    |-- 4. 【RAG】自动检索相关知识库
    |-- 5. 【RAG】将检索结果注入上下文
    |-- 6. 添加用户消息到 Agent 状态
    |
    v
Agent.prompt(messages)
    |
    |-- LLM API 调用 (streamSimple)
    |
    v
Agent 发出事件
    |
    |-- message_start (assistant)
    |-- message_update (流式分块)
    |-- tool_execution_start
    |-- tool_execution_end
    |-- message_end
    |-- agent_end
    |
    v
ConversationEngine._handleAgentEvent(event)
    |
    |-- [状态模式] 持久化消息到 MessageStore
    |-- 检查可重试错误
    |-- 检查压缩触发条件
    |-- 发射到对话监听器
    |
    v
WebSocket/SSE 推送到客户端
```

### 7.2 工具执行流

```
LLM 响应包含 tool_call
    |
    v
Agent.beforeToolCall 钩子
    |
    |-- 扩展钩子（tool_call 事件）
    |
    v
ToolRegistry.getToolImplementation(toolName)
    |
    v
执行工具实现
    |
    |-- 工具在隔离上下文中运行
    |-- 可能是异步的（API 调用、数据库查询）
    |
    v
Agent.afterToolCall 钩子
    |
    |-- 扩展钩子（tool_result 事件）
    |
    v
工具结果添加到对话上下文
    |
    v
Agent 继续（下一轮带工具结果的 LLM 调用）
```

### 7.3 上下文压缩流

#### 无状态模式（仅内存）

```
Agent 响应表明上下文接近限制
    |
    v
ConversationEngine._checkCompaction()
    |
    |-- 从 agent.state.messages 计算上下文 tokens
    |-- 与阈值比较
    |
    v
如果超过阈值：
    |
    v
CompactionEngine.compact(messages)
    |
    |-- 1. 直接从 agent.state.messages 读取消息
    |-- 2. 选择较旧消息进行摘要
    |-- 3. 调用 LLM 生成摘要
    |-- 4. 用摘要消息替换被摘要的消息
    |--    agent.state.messages = [summary, ...recentMessages]
    |
    v
继续带压缩后上下文的对话
```

#### 有状态模式（持久化存储）

```
Agent 响应表明上下文接近限制
    |
    v
ConversationEngine._checkCompaction()
    |
    |-- 从消息历史计算上下文 tokens
    |-- 与阈值比较
    |
    v
如果超过阈值：
    |
    v
CompactionEngine.compact(conversationId)
    |
    |-- 1. 从 MessageStore 获取消息
    |-- 2. 选择较旧消息进行摘要
    |-- 3. 调用 LLM 生成摘要
    |-- 4. 存储压缩记录到 MessageStore
    |-- 5. 用摘要 + 近期消息更新 agent.state.messages
    |
    v
更新对话状态
    |
    v
构建新上下文：摘要 + 近期消息
    |
    v
继续带压缩后上下文的对话
```

### 7.4 RAG 检索流

```
用户发送消息
    |
    v
ConversationEngine.prompt()
    |
    v
【自动检索】injectRetrievedContext()
    |
    |-- 1. 获取租户绑定的知识库列表
    |-- 2. 将用户查询向量化
    |-- 3. 在向量存储中执行相似度检索
    |-- 4. 【可选】关键词检索（BM25）
    |-- 5. 【可选】RRF 融合 dense + sparse 结果
    |-- 6. 【可选】重排序（rerank）
    |-- 7. 过滤低于阈值的片段
    |
    v
将检索到的文档片段格式化为上下文消息
    |
    v
注入到 agent.state.messages（system/custom 角色）
    |
    v
Agent.prompt() 发送给 LLM（含检索上下文）
    |
    v
LLM 生成带引用的回答
```

---

## 8. 运行模式对比与选择

### 8.1 功能对比

| 功能 | 无状态模式 | 有状态模式 |
|------|-----------|-----------|
| **消息存储** | 仅内存（`agent.state.messages`） | 外部数据库（PostgreSQL/Redis） |
| **对话恢复** | 不支持；断开即数据丢失 | 支持；可在任意 Worker 恢复 |
| **历史 API** | 不可用 | 完整分页支持 |
| **跨设备同步** | 不支持 | 支持 |
| **上下文压缩** | 内存数组变换 | 持久化压缩记录 |
| **会话列表** | 不可用 | 按用户/租户查询 |
| **Worker 重启影响** | 所有对话丢失 | 对话可恢复 |
| **资源开销** | 极低（每 1000 轮约 400KB） | DB 连接 + I/O + 存储 |
| **吞吐量** | 更高（无 DB 写入） | 较低（每条消息 DB 写入） |
| **延迟** | 更低（无持久化延迟） | 略高（异步 DB 写入） |

### 8.2 决策矩阵

| 场景 | 推荐模式 | 原因 |
|------|---------|------|
| 单次 API（单轮问答） | **无状态** | 无需持久化 |
| 实时流式聊天，临时会话 | **无状态** | 断开 = 会话结束 |
| 需要历史记录的客服聊天 | **有状态** | 客服需要上下文 + 交接 |
| 多轮编码助手 | **有状态** | 用户期望稍后恢复 |
| 高吞吐自动化流水线 | **无状态** | 最大化吞吐量 |
| 跨设备同步的移动应用 | **有状态** | 任意设备恢复 |
| 有审计要求的内部工具 | **有状态** | 合规需要持久化 |

### 8.3 配置

```typescript
// 全局默认（应用于所有对话）
const factory = new ConversationFactory({
  sharedServices,
  defaultPersistenceMode: "stateless", // 或 "stateful"
});

// 每对话覆盖
const engine = await factory.create({
  conversationId: "conv-123",
  userId: "user-456",
  persistenceMode: "stateful", // 覆盖全局默认
});

// 每租户默认
const configProvider: ConfigProvider = {
  getTenantConfig(tenantId, key, defaultValue) {
    if (key === "persistenceMode") {
      // 租户 A 付费使用有状态，租户 B 使用无状态
      return tenantConfig[tenantId]?.persistenceMode ?? defaultValue;
    }
    return defaultValue;
  },
};
```

### 8.4 混合模式：懒持久化

对于大部分对话是临时的但部分需要恢复的场景，可使用**懒持久化**策略：

```typescript
class LazyPersistenceEngine extends ConversationEngine {
  // 以无状态模式启动
  private persistenceMode: PersistenceMode = "stateless";

  // 用户显式保存或订阅时提升为有状态
  async promoteToStateful(): Promise<void> {
    if (this.persistenceMode === "stateful") return;

    // 将当前内存状态刷入存储
    await this.messageStore?.appendMessages(
      this.conversationId,
      this.agent.state.messages,
    );
    this.persistenceMode = "stateful";
  }
}
```

---

## 9. 并发模型

### 9.1 每对话串行执行

单个对话内，事件串行处理以保持顺序：

```typescript
// 每对话串行队列
private agentEventQueue: Promise<void> = Promise.resolve();

private enqueueEvent(event: AgentEvent): void {
  this.agentEventQueue = this.agentEventQueue.then(
    () => this.processEvent(event),
    () => this.processEvent(event),
  );
}
```

这保留了当前框架的确切语义，同时隔离了对话。

### 9.2 跨对话并行

对话完全独立。每个在自己的事件循环轮次中运行：

```typescript
// Worker 事件循环处理多个对话
class Worker {
  private conversations: Map<string, ConversationEngine>;

  async handleMessage(conversationId: string, message: UserMessage): Promise<void> {
    const conversation = this.conversations.get(conversationId);
    if (!conversation) throw new Error("对话不存在");

    // 立即返回；对话在自己的串行队列上处理消息
    await conversation.prompt(message.text);
  }
}
```

Node.js 的单线程事件循环天然支持这一点：当对话 A 等待 LLM API 响应时，对话 B 可以处理事件。

### 9.3 LLM 请求并发

LLM API 调用是主要瓶颈。设计考虑：

| 策略 | 描述 |
|------|------|
| **连接池** | 每模型提供商维护 HTTP/2 连接池 |
| **速率限制** | 每租户速率限制防止滥用 |
| **请求队列** | 接近速率限制时排队请求 |
| **流式** | 始终使用流式减少首字节时间 |
| **背压** | Worker 过载时拒绝新 prompt |

### 9.4 资源限制

```typescript
interface WorkerResourceLimits {
  maxConversations: number;        // 最大活跃对话数
  maxLlmRequestsPerMinute: number; // LLM API 调用速率限制
  maxTokensPerMinute: number;      // Token 吞吐量限制
  maxToolExecutionTime: number;    // 工具超时
  maxEventQueueDepth: number;      // 背压阈值
}
```

---

## 10. 事件系统映射

### 10.1 当前事件 -> 云事件

| 当前事件（AgentSession） | 云等价事件 | 投递方式 |
|--------------------------|-----------|---------|
| `agent_start` | `conversation.turn.start` | WebSocket/SSE |
| `agent_end` | `conversation.turn.end` | WebSocket/SSE |
| `turn_start` | `conversation.turn.start` | WebSocket/SSE |
| `turn_end` | `conversation.turn.end` | WebSocket/SSE |
| `message_start` | `conversation.message.start` | WebSocket/SSE |
| `message_update` | `conversation.message.delta` | WebSocket/SSE |
| `message_end` | `conversation.message.complete` | WebSocket/SSE |
| `tool_execution_start` | `conversation.tool.start` | WebSocket/SSE |
| `tool_execution_update` | `conversation.tool.progress` | WebSocket/SSE |
| `tool_execution_end` | `conversation.tool.complete` | WebSocket/SSE |
| `compaction_start` | `conversation.compaction.start` | WebSocket/SSE |
| `compaction_end` | `conversation.compaction.complete` | WebSocket/SSE |
| `auto_retry_start` | `conversation.retry.start` | WebSocket/SSE |
| `auto_retry_end` | `conversation.retry.complete` | WebSocket/SSE |
| `queue_update` | `conversation.queue.update` | WebSocket/SSE |

### 10.2 事件 Schema

```typescript
interface CloudEvent {
  eventId: string;
  conversationId: string;
  userId: string;
  tenantId?: string;
  timestamp: string;
  type: string;
  payload: unknown;
}

interface MessageDeltaEvent extends CloudEvent {
  type: "conversation.message.delta";
  payload: {
    messageId: string;
    role: "assistant";
    delta: string;
    finishReason?: "stop" | "length" | "tool_calls" | "error";
  };
}

interface ToolCompleteEvent extends CloudEvent {
  type: "conversation.tool.complete";
  payload: {
    toolCallId: string;
    toolName: string;
    result: unknown;
    isError: boolean;
    durationMs: number;
  };
}
```

### 10.3 事件总线实现

用于跨 Worker 事件传播（例如对话从 Worker A 迁移到 Worker B）：

```typescript
interface EventBus {
  // 发布事件到所有订阅者
  publish(event: CloudEvent): Promise<void>;

  // 订阅特定对话的事件
  subscribe(
    conversationId: string,
    handler: (event: CloudEvent) => void,
  ): () => void;

  // 订阅所有事件（用于监控）
  subscribeAll(handler: (event: CloudEvent) => void): () => void;
}

// Redis 后端实现
class RedisEventBus implements EventBus {
  private redis: Redis;
  private localEmitter: EventEmitter;

  async publish(event: CloudEvent): Promise<void> {
    // 发布到 Redis 频道
    await this.redis.publish(
      `events:${event.conversationId}`,
      JSON.stringify(event),
    );
    // 同时本地发射给同 Worker 订阅者
    this.localEmitter.emit(event.conversationId, event);
  }

  subscribe(conversationId: string, handler: (event: CloudEvent) => void): () => void {
    // 订阅 Redis 频道
    const subscriber = this.redis.duplicate();
    subscriber.subscribe(`events:${conversationId}`);
    subscriber.on("message", (_, message) => handler(JSON.parse(message)));

    // 同时本地监听
    this.localEmitter.on(conversationId, handler);

    return () => {
      subscriber.unsubscribe();
      subscriber.quit();
      this.localEmitter.off(conversationId, handler);
    };
  }
}
```

---

## 11. 扩展系统适配

### 11.1 当前扩展钩子

当前框架通过 `ExtensionRunner` 提供以下扩展钩子：

| 钩子 | 用途 | 云适配 |
|------|------|--------|
| `before_agent_start` | 修改系统提示词或注入消息 | 原样支持 |
| `tool_call` | 拦截/阻止工具调用 | 原样支持 |
| `tool_result` | 修改工具结果 | 原样支持 |
| `input` | 转换或阻止用户输入 | 原样支持 |
| `context` | 发送给 LLM 前修改消息 | 原样支持（RAG 扩展点） |
| `before_provider_request` | 修改 LLM API 负载 | 原样支持 |
| `resources_discover` | 发现 Skill/Prompt/Theme | 替换文件扫描为 API 调用 |
| `session_start` / `session_shutdown` | 生命周期事件 | 原样支持 |
| `session_before_compact` | 自定义压缩逻辑 | 原样支持 |
| `agent_start` / `agent_end` | 轮次生命周期 | 原样支持 |
| `message_start` / `message_end` / `message_update` | 消息流式 | 原样支持 |
| `turn_start` / `turn_end` | 轮次边界 | 原样支持 |
| `user_bash` | 拦截 bash 命令 | 移除（云 Agent 无 bash） |

### 11.2 已移除/适配的概念

| 当前概念 | 云状态 | 原因 |
|---------|--------|------|
| `ExtensionUIContext` | **已移除** | 云 Agent 无 TUI |
| `select`, `confirm`, `input` | **已移除** | 无法进行同步用户交互 |
| `setFooter`, `setHeader`, `setTitle` | **已移除** | 无终端 UI |
| `setWidget`, `setEditorComponent` | **已移除** | 无 TUI 组件 |
| `ExtensionCommandContext` (`newSession`, `fork`, `switchSession`, `navigateTree`) | **已适配** | 操作通过 API 而非直接方法调用 |
| `session_before_switch` / `session_before_fork` | **已移除** | 会话切换是 API 层关注，非扩展关注 |
| `session_tree` | **已移除** | 树导航是客户端关注 |

### 11.3 云扩展 API

```typescript
interface CloudExtensionContext {
  // 对话上下文
  conversationId: string;
  userId: string;
  tenantId?: string;

  // 对话状态只读访问
  getMessages(): Promise<ConversationMessage[]>;
  getModel(): Model | undefined;
  getSystemPrompt(): string;

  // 动作
  sendMessage(message: CustomMessage): Promise<void>;
  setActiveTools(toolNames: string[]): void;

  // 服务
  modelRegistry: ModelRegistry;
  skillRegistry: SkillRegistry;
  knowledgeBaseRegistry: KnowledgeBaseRegistry;  // RAG 知识库

  // 事件
  emit(event: ExtensionEvent): Promise<void>;
}

interface CloudExtension {
  name: string;
  version: string;

  // 钩子处理器
  onBeforeAgentStart?(
    event: BeforeAgentStartEvent,
    context: CloudExtensionContext,
  ): Promise<BeforeAgentStartResult | undefined>;

  onToolCall?(
    event: ToolCallEvent,
    context: CloudExtensionContext,
  ): Promise<ToolCallResult | undefined>;

  onToolResult?(
    event: ToolResultEvent,
    context: CloudExtensionContext,
  ): Promise<ToolResultModification | undefined>;

  // RAG 扩展：自定义检索逻辑
  onContext?(
    event: ContextEvent,
    context: CloudExtensionContext,
  ): Promise<ContextEventResult | undefined>;

  // 工具注册
  tools?: ToolDefinition[];
}
```

---

## 12. 系统提示词构建

### 12.1 保留的逻辑

`system-prompt.ts` 中的 `buildSystemPrompt()` 函数完全可复用。其逻辑：

1. 从基础系统提示词模板开始
2. 注入可用工具及其一行描述
3. 根据可用工具注入指南
4. 追加项目上下文文件（AGENTS.md、CLAUDE.md 等价物）
5. 追加 Skill 段（通过 `formatSkillsForPrompt()`）
6. 追加日期和工作目录

### 12.2 云适配

| 组件 | 当前 | 云端 |
|------|------|------|
| 基础提示词 | 硬编码在 `system-prompt.ts` | 从配置或模板存储加载 |
| 工具描述 | 从 `toolSnippets` 生成 | 从 `ToolRegistry` 生成 |
| 上下文文件 | 从 `cwd` 层级扫描 | 从租户配置或数据库加载 |
| Skill | 从文件系统加载 | 从 `SkillRegistry` 缓存加载 |
| 日期/工作目录 | `new Date().toISOString()`, `process.cwd()` | 服务器时间，租户特定上下文 |

### 12.3 租户感知的提示词构建

```typescript
async function buildSystemPromptForConversation(
  conversationId: string,
  tenantId: string | undefined,
  services: SharedServices,
): Promise<string> {
  const config = services.configProvider;
  const skills = services.skillRegistry.getSkills(tenantId);
  const tools = services.toolRegistry.getToolsForConversation(conversationId, tenantId);

  // 租户特定的上下文文件
  const contextFiles = tenantId
    ? await services.configProvider.getTenantContextFiles(tenantId)
    : [];

  // 租户配置中的自定义系统提示词
  const customPrompt = config.getTenantConfig(tenantId, "systemPrompt", undefined);

  return buildSystemPrompt({
    customPrompt,
    selectedTools: tools.map((t) => t.name),
    toolSnippets: buildToolSnippets(tools),
    promptGuidelines: config.getTenantConfig(tenantId, "guidelines", []),
    contextFiles,
    skills,
    cwd: config.getTenantConfig(tenantId, "contextDirectory", "/"),
  });
}
```

---

## 13. RAG 知识库集成详解

### 13.1 RAG 在对话中的位置

RAG 不是独立模块，而是对话流程的有机组成部分。其核心价值是**在每一轮对话中，自动将最相关的领域知识注入 LLM 上下文**。

```
用户输入 -> 【检索】-> 相关知识片段 -> 【注入】-> LLM 上下文 -> LLM 回答
                ^
                |
        向量数据库（语义检索）
```

### 13.2 三种检索触发策略

| 策略 | 触发时机 | 适用场景 | 实现方式 |
|------|---------|---------|---------|
| **自动检索** | 每轮用户消息自动触发 | 通用问答、客服 | `before_agent_start` 钩子 |
| **按需检索** | LLM 通过工具调用触发 | 复杂查询、多步推理 | `search_knowledge_base` 工具 |
| **混合检索** | 自动 + 按需结合 | 高精度场景 | 自动检索 + LLM 可选二次检索 |

### 13.3 检索结果注入格式

```typescript
// 方式 1：作为 system 消息注入（推荐）
const systemContext: AgentMessage = {
  role: "system",
  content: `## 参考文档\n\n${chunks.map(c =>
    `[来源: ${c.sourceDocument.title}]\n${c.content}`
  ).join("\n\n---\n\n")}`,
};

// 方式 2：作为 custom 消息注入（更灵活）
const customContext: CustomMessage = {
  role: "custom",
  customType: "retrieved_context",
  content: formatChunks(chunks),
  display: false,  // 不展示给用户
};
```

### 13.4 引用与溯源

LLM 回答应包含对知识库文档的引用：

```typescript
interface CitationConfig {
  enabled: boolean;
  format: "inline" | "footnote" | "markdown_link";
  maxCitations: number;
}

// 在系统提示词中指导 LLM 引用
const citationInstruction = `
回答时请遵循以下引用规则：
1. 当使用知识库文档中的信息时，在相关内容后用 [来源: 文档标题] 标注
2. 如果信息来自多个文档，标注所有相关来源
3. 未使用知识库信息时，无需标注
4. 不确定信息来源时，标注 [来源: 推测]
`;
```

### 13.5 知识库管理 API

```typescript
// POST /api/v1/knowledge-bases
// 创建知识库
interface CreateKnowledgeBaseRequest {
  name: string;
  description?: string;
  tenantId?: string;
  embeddingModel?: string;        // "text-embedding-3-small"
  embeddingDimension?: number;    // 1536
  chunkSize?: number;             // 512
  chunkOverlap?: number;          // 50
}

// POST /api/v1/knowledge-bases/:id/documents
// 上传文档到知识库
interface UploadDocumentRequest {
  file: File;                     // PDF, DOCX, MD, TXT
  title?: string;
  metadata?: Record<string, unknown>;
}

// GET /api/v1/knowledge-bases/:id/documents
// 列出知识库文档

// DELETE /api/v1/knowledge-bases/:id/documents/:docId
// 删除文档

// POST /api/v1/knowledge-bases/:id/search
// 直接检索知识库
interface SearchKnowledgeBaseRequest {
  query: string;
  topK?: number;
  filters?: Record<string, unknown>;
}

interface SearchKnowledgeBaseResponse {
  chunks: DocumentChunk[];
  totalChunks: number;
}
```

### 13.6 多租户知识库隔离

```typescript
interface KnowledgeBaseACL {
  // 知识库访问控制
  canAccess(kbId: string, tenantId?: string, userId?: string): boolean;

  // 租户默认可访问的知识库
  getDefaultKnowledgeBases(tenantId: string): string[];

  // 用户自定义知识库绑定
  getUserKnowledgeBases(userId: string): string[];
}

// 实现：行级安全（PostgreSQL RLS）或命名空间隔离
// pgvector 表中的 tenant_id 列用于过滤
```

---

## 14. 部署架构

### 14.1 Kubernetes 部署

```yaml
# conversation-worker 部署
apiVersion: apps/v1
kind: Deployment
metadata:
  name: conversation-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: conversation-worker
  template:
    metadata:
      labels:
        app: conversation-worker
    spec:
      containers:
        - name: worker
          image: cloud-agent-worker:latest
          env:
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: redis-credentials
                  key: url
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: db-credentials
                  key: url
            - name: MAX_CONVERSATIONS_PER_WORKER
              value: "100"
            - name: IDLE_TIMEOUT_MS
              value: "300000"
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "2000m"
---
# WebSocket 网关（独立或共置）
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ws-gateway
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: gateway
          image: cloud-agent-gateway:latest
          ports:
            - containerPort: 8080
```

### 14.2 扩展策略

| 指标 | 扩展触发条件 | 动作 |
|------|-------------|------|
| 活跃对话数 | > 80% Worker 容量 | Worker +1 |
| LLM 请求队列深度 | > 50 排队请求 | Worker +1 |
| 内存使用 | > 80% | Worker +1 |
| 空闲对话比例 | > 50% 空闲 | Worker -1 |
| 错误率 | > 5% | 告警，不自动扩展 |

### 14.3 会话亲和性

对于 WebSocket 连接，使用粘性会话将对话保持在同一 Worker：

```yaml
apiVersion: v1
kind: Service
metadata:
  name: conversation-worker
spec:
  sessionAffinity: ClientIP
  sessionAffinityConfig:
    clientIP:
      timeoutSeconds: 300
```

或者使用独立的 WebSocket 网关，通过 Redis pub/sub 将消息路由到 Worker，允许任意 Worker 处理任意对话。

---

## 15. 可观测性

### 15.1 指标

| 指标 | 类型 | 标签 |
|------|------|------|
| `conversations.active` | Gauge | worker_id, tenant_id |
| `conversations.total` | Counter | tenant_id |
| `messages.sent` | Counter | tenant_id, model_provider |
| `messages.received` | Counter | tenant_id, model_provider |
| `llm.requests.duration` | Histogram | model_provider, model_id |
| `llm.tokens.input` | Counter | model_provider, model_id |
| `llm.tokens.output` | Counter | model_provider, model_id |
| `tools.executed` | Counter | tool_name, tenant_id |
| `tools.execution.duration` | Histogram | tool_name |
| `compactions.triggered` | Counter | tenant_id, reason |
| `retries.attempted` | Counter | tenant_id, error_type |
| `events.processed` | Counter | event_type |
| `event_queue.depth` | Gauge | conversation_id |
| `rag.retrievals` | Counter | knowledge_base_id, tenant_id |
| `rag.retrieval.duration` | Histogram | knowledge_base_id |
| `rag.chunks.retrieved` | Histogram | knowledge_base_id |

### 15.2 分布式追踪

每对话轮次应为追踪 span：

```
Trace: conversation-turn
  Span: prompt-received
  Span: system-prompt-build
  Span: rag-retrieval          // RAG 检索
    Span: embedding-query
    Span: vector-search
    Span: rerank
  Span: llm-request（流式事件的父 span）
    Span: tool-call-1
    Span: tool-call-2
  Span: persist-messages
  Span: check-compaction
```

### 15.3 日志

```typescript
// 每对话结构化日志
logger.info({
  event: "conversation.turn.complete",
  conversationId: "conv-123",
  userId: "user-456",
  tenantId: "tenant-789",
  model: "anthropic/claude-sonnet-4",
  durationMs: 2450,
  inputTokens: 1024,
  outputTokens: 512,
  toolCalls: 2,
  ragChunks: 3,              // RAG 检索到的片段数
});
```

---

## 16. 安全性

### 16.1 租户隔离

- 每租户的对话在数据库层面隔离（行级安全或独立 schema）
- 租户特定工具和 Skill 加载到独立注册表
- API Key 按租户限定范围
- 速率限制按租户应用

### 16.2 输入验证

- 所有用户输入在添加到对话上下文前经过清理
- 工具参数按 JSON Schema 验证
- 强制执行最大消息大小限制
- 最大对话长度（轮数）可按租户配置

### 16.3 输出防护

- `output-guard.ts` 逻辑保留并增强
- PII 检测与脱敏
- 内容策略执行
- 工具结果过滤

### 16.4 知识库安全

- 知识库按租户隔离
- 文档访问控制列表（ACL）
- 检索结果按租户过滤
- 敏感文档标记与额外审核

---

## 17. 迁移路径

### 17.1 从当前框架迁移

| 步骤 | 动作 | 工作量 | 模式 |
|------|------|--------|------|
| 1 | 将 `AgentSession` 事件循环逻辑提取到 `ConversationEngine` | 中 | 两者 |
| 2 | 添加 `persistenceMode` 配置到 `ConversationEngine` | 低 | 两者 |
| 3 | 实现 `ConversationStore` 和 `MessageStore` 适配器 | 中 | 仅状态 |
| 4 | 适配 `compact()` 以支持内存（无状态）和存储（有状态） | 低 | 两者 |
| 5 | 实现 `SkillRegistry`（S3/DB 后端） | 低 | 两者 |
| 6 | 实现 `CloudModelRegistry`（无 `AuthStorage`） | 低 | 两者 |
| 7 | 从扩展系统移除 TUI 特定代码 | 低 | 两者 |
| 8 | 添加 WebSocket/SSE 网关层 | 中 | 两者 |
| 9 | 添加 Redis pub/sub 用于跨 Worker 事件 | 低 | 两者 |
| 10 | **添加 `KnowledgeBaseRegistry` 和 RAG 检索流** | **中** | **两者** |
| 11 | **实现文档索引器和向量存储适配器** | **中** | **两者** |
| 12 | **在系统提示词构建中集成知识库描述** | **低** | **两者** |
| 13 | 添加指标和追踪 | 低 | 两者 |
| 14 | 性能测试和调优 | 高 | 两者 |

### 17.2 复用清单

| 组件 | 复用 | 模式 | 说明 |
|-----------|-------|------|-------|
| `Agent` (pi-agent-core) | 完整 | 两者 | 无需修改 |
| `AgentSession.prompt()` 逻辑 | 完整 | 两者 | 复制事件循环、工具展开、重试逻辑 |
| `AgentSession.compact()` | 适配 | 两者 | 无状态：直接内存变更。有状态：+ MessageStore |
| `buildSystemPrompt()` | 完整 | 两者 | 无需修改 |
| `formatSkillsForPrompt()` | 完整 | 两者 | 无需修改 |
| `ExtensionRunner.emit()` | 完整 | 两者 | 移除 UI 上下文，保留所有其他钩子 |
| `ExtensionRunner.emitToolCall()` | 完整 | 两者 | 无需修改 |
| `ExtensionRunner.emitToolResult()` | 完整 | 两者 | 无需修改 |
| `ToolDefinition` 类型 | 完整 | 两者 | 无需修改 |
| `EventBus` | 部分 | 两者 | 添加 Redis 后端 |
| `loadSkills()` | 部分 | 两者 | 保留解析逻辑，替换文件 I/O |
| `SessionManager` | 无 | 有状态 | 替换为 `ConversationStore` + `MessageStore` |
| `SessionManager` | 跳过 | 无状态 | 不需要 |
| `SettingsManager` | 无 | 两者 | 替换为 `ConfigProvider` |
| `AuthStorage` | 无 | 两者 | 替换为密钥管理 |
| `ResourceLoader` | 部分 | 两者 | 保留覆盖逻辑，替换文件扫描 |
| `bash-executor.ts` | 无 | 两者 | 云 Agent 不适用 |
| `tools/*` (read/write/edit/grep/find/ls) | 无 | 两者 | 替换为云特定工具 |
| **RAG 新增** | **新增** | **两者** | **KnowledgeBaseRegistry、DocumentIndexer、Retriever、向量存储适配** |

---

## 18. API 设计

### 18.1 REST API

```typescript
// POST /api/v1/conversations
// 创建新对话
interface CreateConversationRequest {
  userId: string;
  tenantId?: string;
  model?: string;              // "anthropic/claude-sonnet-4"
  thinkingLevel?: string;      // "off" | "minimal" | "low" | "medium" | "high"
  systemPrompt?: string;       // 覆盖默认系统提示词
  tools?: string[];            // 活跃工具名称
  persistenceMode?: "stateful" | "stateless";  // 租户配置的默认值
  knowledgeBaseIds?: string[]; // 绑定的知识库
  metadata?: Record<string, unknown>;
}

interface CreateConversationResponse {
  conversationId: string;
  createdAt: string;
  status: "active";
  persistenceMode: "stateful" | "stateless";
}

// POST /api/v1/conversations/:id/messages
// 发送消息到对话
interface SendMessageRequest {
  content: string;
  role?: "user";
  attachments?: Attachment[];
}

// GET /api/v1/conversations/:id/messages
// 获取对话历史
interface GetMessagesResponse {
  messages: ConversationMessage[];
  hasMore: boolean;
  nextCursor?: string;
}

// POST /api/v1/conversations/:id/abort
// 中止当前操作

// DELETE /api/v1/conversations/:id
// 删除对话
```

### 18.2 WebSocket API

```typescript
// 客户端 -> 服务端
interface ClientMessage {
  type: "message" | "steer" | "abort" | "ping";
  conversationId: string;
  payload: unknown;
}

// 服务端 -> 客户端
interface ServerMessage {
  type: "event" | "error" | "pong";
  conversationId: string;
  eventType?: string;
  payload: unknown;
  timestamp: string;
}

// 连接流程：
// 1. 客户端打开 WebSocket 连接到 /ws
// 2. 客户端发送：{ type: "subscribe", conversationId: "conv-123" }
// 3. 服务端开始流式传输该对话的事件
// 4. 客户端发送：{ type: "message", conversationId: "conv-123", payload: { content: "Hello" } }
// 5. 服务端流式传输：message_start -> message_delta * N -> message_end -> turn_end
```

---

## 19. 附录：接口定义

### 19.1 完整 ConversationEngine 接口

```typescript
interface ConversationEngine {
  // 标识
  readonly conversationId: string;
  readonly userId: string;
  readonly tenantId?: string;

  // 消息
  prompt(text: string, options?: PromptOptions): Promise<void>;
  steer(text: string, images?: ImageContent[]): Promise<void>;
  followUp(text: string, images?: ImageContent[]): Promise<void>;
  sendCustomMessage(message: CustomMessage, options?: SendOptions): Promise<void>;

  // 控制
  abort(): Promise<void>;
  clearQueue(): { steering: string[]; followUp: string[] };

  // 状态
  readonly isStreaming: boolean;
  readonly isCompacting: boolean;
  readonly isRetrying: boolean;
  readonly pendingMessageCount: number;
  getContextUsage(): ContextUsage | undefined;
  getStats(): ConversationStats;

  // 工具
  getActiveToolNames(): string[];
  setActiveTools(toolNames: string[]): void;
  getAllTools(): ToolInfo[];

  // 事件
  subscribe(listener: ConversationEventListener): () => void;

  // 生命周期
  dispose(): void;
}
```

### 19.2 共享服务接口

```typescript
interface SharedServices {
  modelRegistry: CloudModelRegistry;
  skillRegistry: SkillRegistry;
  toolRegistry: ToolRegistry;
  knowledgeBaseRegistry: KnowledgeBaseRegistry;
  configProvider: ConfigProvider;
  eventBus: EventBus;
  metricsCollector: MetricsCollector;
  logger: Logger;
}
```

### 19.3 存储接口

```typescript
interface ConversationStore {
  create(record: ConversationRecord): Promise<void>;
  get(id: string): Promise<ConversationRecord | null>;
  update(id: string, updates: Partial<ConversationRecord>): Promise<void>;
  listByUser(userId: string, options?: ListOptions): Promise<ConversationRecord[]>;
  delete(id: string): Promise<void>;
}

interface MessageStore {
  appendMessage(conversationId: string, message: ConversationMessage): Promise<string>;
  appendEvent(conversationId: string, event: ConversationEvent): Promise<string>;
  getMessages(conversationId: string, options?: MessageQueryOptions): Promise<ConversationMessage[]>;
  getMessageHistory(conversationId: string): Promise<ConversationMessage[]>;
  getEvents(conversationId: string): Promise<ConversationEvent[]>;
  markCompacted(conversationId: string, upToMessageId: string, summary: string): Promise<void>;
}
```

### 19.4 RAG 知识库接口

```typescript
interface KnowledgeBaseRegistry {
  registerKnowledgeBase(kb: KnowledgeBaseConfig): Promise<void>;
  unregisterKnowledgeBase(kbId: string): void;
  getKnowledgeBases(tenantId?: string): KnowledgeBase[];
  retrieve(query: RetrieveQuery): Promise<RetrieveResult>;
  indexDocuments(kbId: string, documents: Document[]): Promise<void>;
  deleteDocuments(kbId: string, docIds: string[]): Promise<void>;
}

interface VectorStoreAdapter {
  createCollection(name: string, dimension: number): Promise<void>;
  upsert(collection: string, vectors: VectorRecord[]): Promise<void>;
  search(collection: string, queryVector: number[], options: SearchOptions): Promise<SearchResult[]>;
  delete(collection: string, ids: string[]): Promise<void>;
}
```

---

## 20. 总结

本文档提供了一个完整的蓝图，用于将当前单用户、本地文件系统 Agent 框架转变为云原生、多租户、高并发系统。关键架构决策包括：

1. **实例隔离**：每对话获得自己的 `ConversationEngine` + `Agent` 实例，消除所有共享可变状态。

2. **双运行模式**：框架支持 `有状态`（持久化历史、恢复、跨设备同步）和 `无状态`（仅内存、最大吞吐量、临时）两种模式，通过配置切换。核心 Agent 循环在两种模式下完全一致；仅持久化层不同。

3. **共享只读服务**：`ModelRegistry`、`SkillRegistry`、`ToolRegistry`、`KnowledgeBaseRegistry` 和 `ConfigProvider` 是每 Worker 单例，启动时加载并缓存到内存。无论持久化模式如何都会复用。

4. **可插拔存储**：存储适配器（`ConversationStore`、`MessageStore`）是可选的，仅在有状态模式下激活。在无状态模式下，`agent.state.messages` 是唯一数据源，消除所有数据库 I/O 开销。

5. **RAG 知识库**：通过 `KnowledgeBaseRegistry` 提供完整的检索增强生成能力，支持向量存储（pgvector、Milvus、Qdrant 等）、混合检索（语义 + 关键词）、自动/按需检索策略，以及多租户隔离。RAG 深度集成到系统提示词构建、`before_agent_start` 钩子、工具层和扩展系统中。

6. **保留的事件架构**：基于订阅的事件模型按对话保留，添加 Redis pub/sub 用于跨 Worker 事件传播。

7. **移除本地假设**：TUI 代码、bash 执行、本地文件操作和基于文件系统的资源加载被替换为云原生等价物。

最终系统可在多个 Worker 上支持数千个并发对话，同时保留使当前框架强大的工具生态、Skill 注入、扩展钩子、系统提示词构建、事件驱动架构和 RAG 知识库能力。运营方可为高通量临时任务选择无状态模式，或为持久化多轮对话选择有状态模式，均无需修改核心 Agent 逻辑。
