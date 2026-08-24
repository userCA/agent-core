# Dynamic Workflows：AI 软件工程的新范式

> 来源：
> - [爱海贼的无处不在 - 微信公众号](https://mp.weixin.qq.com/s/Xs7e3goFNUhJg5xEiO5YMA)
> - [Thariq Shihipar - Dynamic Workflows 官方博客](https://x.com/trq212/status/2061907337154367865)（Anthropic 技术团队成员）
> 整理时间：2026-08-07

---

## 一、什么是 Dynamic Workflows

Dynamic Workflows（动态工作流）是 Anthropic 随 Claude Opus 4.8 发布的一项新能力。它不是一个"更强的代码助手"，而是一种**全新的软件工程执行范式**：

> 从「单 Agent 对话式编程」演进到「可持久化、可恢复、可验证的大规模并行 Agent 集群编排系统」。

其本质是一个**能够自动编排数十到数百个并行子智能体（Subagents）的执行框架**。Claude 在后台动态生成并执行一段 JavaScript 脚本，中间步骤和临时结果存储在脚本变量中，而不是堆积在主对话的上下文窗口中，最终只有经过验证的结论才返回给用户。

### 核心定位

| 能力 | 解决的问题 |
|------|-----------|
| **MCP** | AI 如何连接世界 |
| **Skills** | AI 如何沉淀经验 |
| **Dynamic Workflows** | **AI 如何组织大规模工作** |

Dynamic Workflows 标志着开发模式正在从"单一对话式 Agent"迈向"大规模并行智能体协作网络"。

--

## 二、快速体验

### 2.1 环境准备

更新 Claude Code 到最新版本：

```bash
npm install -g @anthropic-ai/claude-code
```

进入 Claude Code 命令行界面：

```bash
claude
```

### 2.2 触发方式

根据官方说明，有以下几种触发方式：
1. 提示词中直接包含 **"workflow"** 关键词
2. 使用触发词 **`ultracode`**，确保 Claude Code 创建工作流（极高推理投入 + 自动工作流编排）
3. 调用内置的 `/deep-research` 宏命令

也可通过 `/workflows` 命令查看执行进度。

### 2.3 实战演练：自动化小说生成工作流

以一个小说生成工作流为例，可一键生成：
1. 3 章小说的 Markdown 文档
2. 对应的精美 HTML 网页（支持在线阅读）
3. 小说目录首页

**执行过程与 Agent 调度情况：**

| 步骤 | 阶段 | 新增 Agent | 累计 Agent |
|------|------|-----------|------------|
| 1-2 | 思考构思 + 规划 | 4 | 4 |
| 3 | 生成小说章节（并行 3 章） | 3 | 7 |
| 4 | 生成 HTML 网页（并行 3 章） | 3 | 10 |
| 5 | 写入文件（并行写入） | 3 | 13 |
| 6 | 生成目录页 + 收尾 | 2 | 15 |

最终通过 **15 个 Agent** 协作完成 3 章小说的全套生成。

### 2.4 工作流保存与复用

执行过程中按 `s` 键可保存工作流：

- **`.claude/workflows/`** — 项目目录，团队共享（建议提交 Git）
- **`~/.claude/workflows/`** — 家目录，个人全局可用

保存后提示格式如：

```
Invoke as /xiaoming-workflow or Workflow({name: "xiaoming-workflow"}) in future sessions.
```

保存后在 Claude Code 中输入 `/` 即可在自动补全列表中看到。

### 2.5 进度视图操作

通过 `/workflows` 进入运行列表，可查看各阶段执行进度。相关操作命令：

| 操作 | 说明 |
|------|------|
| `/workflows` | 查看运行中的工作流列表与进度 |
| `s` 键 | 保存当前工作流供后续复用 |
| Agent View | 监控后台执行详情 |

### 2.6 内置工作流：/deep-research

Claude Code 自带开箱即用的 `/deep-research` 工作流，专门用于深度调研（上网 + 读代码 + 交叉验证）：

```bash
/deep-research <你的调研主题>
```

它会自动拆分为几十个 subagent：一批查文档、一批读仓库实际代码、一批跑对照验证，最终汇总成一份带引用的报告。

### 2.7 示例提示词

以下提示词来自官方博客，帮助感受工作流的可能性：

**调试与测试：**
> "这个测试大约每 50 次运行会失败 1 次。设置一个工作流来复现它、形成理论，并在 worktree 中对这些理论做对抗式测试。不要停止，直到有一个理论成立。"

**会话挖掘与规则提炼：**
> "使用一个工作流，浏览我最近 50 次会话，挖掘我反复做出的修正，并把重复出现的修正变成 CLAUDE.md 规则。"

**多视角分析：**
> "拿我的商业计划，运行一个工作流，让不同智能体分别从投资者、客户和竞争对手视角拆解它。"

**批量处理与排序：**
> "这里有一个包含 80 份简历的文件夹。使用一个工作流，为后端岗位排序，并复核前 10 名。用 AskUserQuestion 工具采访我，以确定评分标准。"

**创意生成与筛选：**
> "我需要给这个 CLI 工具起名。使用一个工作流想出一批选项，然后跑一场锦标赛，选出前 3 个。"

**内容验证：**
> "遍历我的博客草稿，使用一个工作流根据代码库验证每一个技术论断。我不想发布任何错误内容。"

---

## 三、为什么需要 Dynamic Workflows

### 3.1 单上下文的三大失败模式

当默认 Claude Code 运行时在同一个上下文窗口里同时规划和执行时，遇到长时间运行、大规模并行或高度结构化的对抗性任务，容易受到以下失败模式影响：

| 失败模式 | 表现 |
|---------|------|
| **智能体偷懒（Agent Laziness）** | Claude 在完成复杂、多部分任务之前就停下来，在只取得部分进展后宣布完成。例如一次安全审查有 50 项，它只处理了 20 项 |
| **自我偏好偏差（Self-Preference Bias）** | Claude 倾向于偏爱自己的结果或发现，尤其在被要求根据评分标准验证或评判这些结果时 |
| **目标漂移（Goal Drift）** | 经过多轮对话后，尤其是发生压缩之后，Claude 逐渐丢失对原始目标的忠实度。每次摘要都会损失信息，边界情况要求或"不要做 X"这样的约束可能丢失 |

### 3.2 上下文卸载（Context Offloading）

Dynamic Workflows 的解决方案：
- 主模型先规划整体目标，然后将计划转换为临时 JavaScript 脚本
- 中间变量、循环逻辑、条件分支**全部保存在 JavaScript 运行时内部**
- 主上下文窗口只保留最终结果，子代理独立执行各自任务

**核心思想：把"计划"从对话搬进代码。不是在扩展 Context Window，而是在绕开 Context Window。**

工作流通过编排多个独立的 Claude 实例（各自拥有自己的上下文窗口和聚焦且隔离的目标）来对抗上述失败模式。

### 3.3 并行扇出（Fan-Out）

动态生成的 JavaScript 脚本能够同时协调数十到数百个并行运行的子代理：

1. **动态任务拆解**：主脚本将高层目标分解为多个可并行执行的子任务
2. **并行子代理分发**：启动多个隔离运行的子代理，实现代码修改或从不同角度分析代码路径

### 3.4 对抗式验证（Adversarial Verification）

AI 代理会生成"反方审查员（Devil's Advocate）"Agent：
- 反驳发现结果
- 寻找安全漏洞
- 尝试破坏代码修改方案

各代理不断迭代，直到逻辑分析结果收敛为统一结论。后台运行时汇总验证后的结果，输出单一统一结论给用户。

> **实战案例：** 有网友使用 127 个 Agent 扫描代码，通过对抗性验证淘汰了 17 条误报。

### 3.5 执行隔离与异步

| 特性 | 说明 |
|------|------|
| **隔离执行** | Runtime 在与对话隔离的环境里执行脚本，中间结果留在脚本变量里，不进 Claude 上下文 |
| **异步后台** | 启动后立即返回任务 id，workflow 在后台运行，主会话仍可交互 |
| **并发受控** | 同时最多 16 个 subagent，多出的排队；整个生命周期总量上限 1000 |
| **上下文干净** | 中间推理默认不回主会话（除非脚本用 `log()` 输出） |
| **可交叉验证** | 可让独立 subagent 互相审查彼此结论后再上报 |
| **模型路由** | 工作流可决定每个智能体使用哪个模型，以及子智能体是否在自己的 worktree 中运行 |
| **断点恢复** | 如果工作流被打断（用户操作或退出终端），恢复会话后可从中断处继续 |

### 3.6 动态工作流 vs 静态工作流

| | 静态工作流 | 动态工作流 |
|---|---|---|
| **构建方式** | 人工预编写（Agent SDK / `claude -p`） | Claude 为当前任务即时编写 |
| **覆盖范围** | 需覆盖所有边界情况，通常更通用 | 为具体用例量身定制 |
| **灵活性** | 修改需求需改代码 | Claude 根据任务动态调整运行框架 |
| **前提条件** | 需要开发者预先设计编排逻辑 | Claude Opus 4.8+ 已足够智能，可自行编写运行框架 |

---

## 四、5W2H 全面解析

### What — 是什么？

一个由 Claude 在后台动态生成并执行的 JavaScript 编排脚本框架，能自动编排数十到数百个并行子智能体，中间步骤存储在脚本变量中，最终只返回经过验证的结论。

### Why — 解决什么问题？

- **突破上下文污染的物理极限**：将执行计划卸载到后台代码，主对话上下文保持整洁（详见第三节三大失败模式）
- **将季度级任务缩短至几天**：通过大规模并发极大缩短工程时间
- **内置对抗性审查提升可靠性**：子智能体互相验证甚至对抗性反驳，直到结果收敛
- **对抗智能体偷懒、自我偏好偏差和目标漂移**：多独立上下文窗口 + 聚焦且隔离的目标

### Who — 谁可以使用？

- **适用人群**：处理超大代码库的开发者、架构师或 AI 工程团队
- **开放范围**：Claude Code（CLI、桌面版、VS Code 扩展）中向 Max、Team 和 Enterprise 计划用户开放；Enterprise 用户需管理员手动开启；也可通过 Claude API 及 Amazon Bedrock、Vertex AI 等云平台使用

### When — 什么时候用？

| 极度适用（大型重活） | 千万别用（杀鸡用牛刀） |
|---------------------|----------------------|
| 数百上千个文件的大型迁移 | 单个文件的微小修改 |
| 代码库级别的全局 Bug 排查 | 修个小 Bug |
| 深度全量安全审计 | 简单的格式化 |

### Where — 在哪里运行？

在**后台隔离环境**中运行。用户会话保持高度响应，可通过 Agent View 或 `/workflows` 监控后台执行进度。

### How — 如何触发与运作？

**触发方式（三种）：**
1. 提示词中直接包含 "workflow" 一词
2. 在 Effort 选项中开启 `ultracode` 模式（极高推理投入 + 自动工作流编排）
3. 调用内置的 `/deep-research` 宏命令

**执行流程：**
接收任务 → 动态分解子任务 → 并行启动子智能体 → 对抗性验证与纠错 → 归总报告

**容错与恢复：**
自动保存检查点（Checkpointing），遇网络中断或人为暂停可从断点恢复。完成的工作流脚本可按 `s` 键保存供团队复用。

### How Much — 消耗与限制

- **Token 消耗极高**：单次大型运行可能消耗数百万甚至几千万 Token
- **硬性并发限制**：最多 16 个智能体并发，单次运行智能体总数封顶 1,000 个

---

## 五、架构对比：四种编排模式

### 5.1 概念对比

| 模式 | 类比 | 核心价值 | 适用场景 |
|------|------|---------|---------|
| **Subagent** | 外派调研员 | 隔离噪音，保持主 AI 头脑清醒 | 读某代码模块、查函数调用链、局部审查 |
| **Skill** | 标准操作手册（SOP） | 沉淀资产，消除随机性 | 生成周报、遵循提交流程、按规范审查 |
| **Agent Teams** | 跨职能敏捷项目组 | 分工协作，步调一致 | 前后端配合、边写代码边写测试、多角度审查 |
| **Workflow** | 代码驱动的自动化工厂 | 规模化与可控性，可执行可复查 | 仓库级漏洞扫描、超大迁移、长尾清理 |

### 5.2 核心区别：谁掌握计划？

| | Subagents / Skills | Dynamic Workflows |
|---|---|---|
| **计划位置** | Claude 上下文中 | JavaScript 脚本代码中 |
| **编排方式** | Claude 逐轮决定下一步 | 脚本持有循环、分支和中间结果 |
| **上下文消耗** | 每个结果进入 Claude 上下文 | 上下文只持有最终答案 |
| **质量模式** | 运行更多 Agent | 对抗性审查、多角度起草后择优 |

> Subagents 是"一个老板带几个工人"，Agent Teams 是"几个团队打配合"，Workflow 是一个**工厂**——上百个工位同时干，**管理跟干活分开**。

---

## 六、脚本 API 与编排模式

### 6.1 核心 API

工作流执行一个 JavaScript 文件，文件里可以使用几个特殊函数来生成并协调子智能体，也包含标准 JavaScript 函数（JSON、Math、Array 等）方便处理数据。

```javascript
// 1. 导出 meta 对象
export const meta = {
  name: 'workflow名称',
  description: '描述',
  phases: ['阶段1', '阶段2', ...]  // 进度显示的阶段
}

// 2. phase() — 分阶段
phase('阶段名称')  // 在进度树中创建新的阶段分组

// 3. agent() — 调用 AI（支持结构化输出）
const result = await agent('提示词', {
  phase: '所属阶段',
  label: '显示标签',
  schema: { /* JSON Schema 约束输出格式 */ }
})

// 4. pipeline() — 并行处理
const results = await pipeline(items, async (item, index) => {
  // 对每个 item 执行操作
  return result
})

// 5. log() — 输出日志
log('消息')  // 显示在进度树中

// 6. args — 获取调用参数
args  // Workflow 调用时传入的参数
```

### 6.2 典型工作流程（以小说生成为例）

```
Phase 1: 思考构思
  └─ agent() 生成故事大纲（schema 约束 JSON 输出）

Phase 2: 生成小说章节
  └─ pipeline() 并行生成 3 章内容

Phase 3: 写入 MD 文档
  └─ pipeline() 并行写入 3 个 .md 文件

Phase 4: 生成 HTML 网页
  └─ pipeline() 并行生成 3 个章节网页

Phase 5: 写入 HTML 文件
  └─ 写入章节 HTML + index.html 目录页
```

### 6.3 完整代码示例

以下为小说生成工作流的完整脚本代码，可保存为 `.claude/workflows/` 下的 `.js` 文件直接使用：

```javascript
export const meta = {
  name: 'novel-workflow',
  description: 'Generate a 3-chapter novel, output md files and HTML pages',
  phases: ['思考构思', '生成小说章节', '写入MD文档', '生成HTML网页', '写入HTML文件'],
}

const chapters = [
  {title: '第一章：意外的相遇', filename: 'chapter1.md', htmlFile: 'chapter1.html'},
  {title: '第二章：校园新生活', filename: 'chapter2.md', htmlFile: 'chapter2.html'},
  {title: '第三章：友谊的力量', filename: 'chapter3.md', htmlFile: 'chapter3.html'}
]

// Phase 1: 思考构思 — agent() 生成故事大纲（schema 约束 JSON 输出）
phase('思考构思')
const plan = await agent(`请构思一部3章小说的整体故事线，给出：
1. 三章各自的剧情概要（每章200字）
2. 主要人物性格设定
3. 故事主线和大结局走向`, {
  phase: '思考构思',
  schema: {
    type: 'object',
    properties: {
      chapterSummaries: {type: 'array', items: {type: 'string'}},
      characterProfiles: {type: 'string'},
      storyArc: {type: 'string'}
    },
    required: ['chapterSummaries', 'characterProfiles', 'storyArc']
  }
})

log('故事构思完成，开始生成各章节...')

// Phase 2: 生成小说章节 — pipeline() 并行生成
phase('生成小说章节')
const mdResults = await pipeline(chapters, async (chapter, index) => {
  const summary = plan.chapterSummaries[index]
  const content = await agent(`请根据以下概要，创作小说《${chapter.title}》的完整内容。
章节概要：${summary}
要求：2000-3000字，Markdown 格式输出。`, {
    phase: '生成小说章节',
    label: `生成${chapter.title}`,
    schema: {type: 'object', properties: {content: {type: 'string'}}, required: ['content']}
  })
  return {chapter, content: content.content, index}
})

// Phase 3: 写入 MD 文档 — pipeline() 并行写入
phase('写入MD文档')
await pipeline(mdResults.filter(Boolean), async (result) => {
  await agent(`请将以下小说内容写入文件 ${result.chapter.filename}。
文件路径：${args[1]}/${result.chapter.filename}`, {
    phase: '写入MD文档',
    label: `写入${result.chapter.filename}`,
    schema: {type: 'object', properties: {success: {type: 'boolean'}}, required: ['success']}
  })
  log(`✓ 已生成: ${result.chapter.filename}`)
})

// Phase 4: 生成 HTML 网页 — pipeline() 并行生成
phase('生成HTML网页')
const htmlResults = await pipeline(mdResults.filter(Boolean), async (result) => {
  const htmlContent = await agent(`请将以下小说内容转换为精美的HTML网页。
小说标题：${result.chapter.title}
要求：HTML5 结构，精美 CSS，响应式设计。`, {
    phase: '生成HTML网页',
    label: `生成HTML-${result.chapter.title}`,
    schema: {type: 'object', properties: {html: {type: 'string'}}, required: ['html']}
  })
  return {chapter: result.chapter, html: htmlContent.html}
})

// Phase 5: 写入 HTML 文件 + 生成目录页
phase('写入HTML文件')
await pipeline(htmlResults.filter(Boolean), async (result) => {
  await agent(`请将以下HTML内容写入文件 ${result.chapter.htmlFile}。`, {
    phase: '写入HTML文件',
    label: `写入${result.chapter.htmlFile}`,
    schema: {type: 'object', properties: {success: {type: 'boolean'}}, required: ['success']}
  })
  log(`✓ 已生成: ${result.chapter.htmlFile}`)
})

// 生成并写入目录页 index.html
const indexHtml = await agent(`请为小说创建一个精美的目录首页HTML。`, {
  phase: '写入HTML文件',
  label: '生成目录页',
  schema: {type: 'object', properties: {html: {type: 'string'}}, required: ['html']}
})

await agent(`请将以下HTML内容写入文件 index.html。`, {
  phase: '写入HTML文件',
  label: '写入index.html',
  schema: {type: 'object', properties: {success: {type: 'boolean'}}, required: ['success']}
})
log('✓ 已生成: index.html (目录页)')

log('全部完成！')
```

### 6.4 六大编排模式

Claude 在构建工作流时，可能会使用并组合以下几种常见模式：

#### 模式 1：分类并执行（Classify & Execute）

使用一个分类器智能体判断任务类型，然后根据任务类型路由到不同智能体或行为。也可以在最后使用分类器判断输出。

```
分类器 Agent → 判断任务类型 → 路由到对应处理 Agent
```

#### 模式 2：扇出并综合（Fan-out & Synthesize）

把一个任务拆成很多更小的步骤，让一个智能体处理每个步骤，然后综合这些结果。在有大量小步骤时特别有用；如果每一步都受益于干净的独立上下文窗口，也很适合这种模式。综合步骤是一道屏障：等待所有扇出的智能体完成，然后把它们的结构化输出合并成一个结果。

```
扇出：Agent-1, Agent-2, ..., Agent-N （并行）
综合：等待全部完成 → 合并结构化输出
```

#### 模式 3：对抗式验证（Adversarial Verification）

对每个生成出来的智能体，再运行一个单独的智能体，根据评分标准或条件对它的输出做对抗式验证。

```
生成 Agent → 输出结果 → 验证 Agent（反方审查）→ 迭代至收敛
```

#### 模式 4：生成并过滤（Generate & Filter）

围绕一个主题生成多个想法，然后根据评分标准或验证结果进行过滤，去重后只返回质量最高、经过测试的想法。

```
生成 N 个想法 → 评分/验证/过滤 → 去重 → 返回最优结果
```

#### 模式 5：锦标赛（Tournament）

不是把工作拆开，而是让智能体围绕同一任务竞争。生成 N 个智能体，每个用不同方法尝试同一任务。然后由评审智能体进行两两评判，直到选出赢家。

```
N 个 Agent 竞争同一任务 → 两两比较评判 → 逐轮淘汰 → 最终赢家
```

#### 模式 6：循环直到完成（Loop Until Done）

对工作量未知的任务，不设置固定轮数，而是循环生成智能体，直到满足停止条件，例如没有新发现，或日志中没有更多错误。

```
循环：生成 Agent → 检查结果 → 未满足停止条件？继续循环
                          └─ 满足停止条件？输出结果
```

### 6.5 工作流脚本保存后的目录结构

```
.claude/
  workflows/
    xxxxxx-workflow.js    # 可执行的 JavaScript 编排脚本
```

工作流脚本落地为文件后，可以进一步做以下扩展：
1. 用 AI 程序自动生成适配 Claude Code 的 Workflows 脚本
2. 编写 Skills 来生成稳定的 Workflows 脚本逻辑
3. 建设 Workflows 市场与周边生态

---

## 七、使用场景

工作流不只在技术工作中有用，在非技术工作中甚至更有用。

### 7.1 迁移与重构

Bun 作者 Jarred Sumner 使用工作流从 Zig 重写成了 Rust：
- 生成约 **75 万行** Rust 代码
- 既有测试套件通过率达到 **99.8%**
- 从首次提交到代码合并仅用 **11 天**

**关键做法：** 把任务拆成一系列需要操作的步骤（调用点、失败测试、模块等）。为每个修复在 worktree 中派生子智能体完成修复，再让另一个智能体做对抗式评审并合并结果。明确告诉智能体不要使用资源密集型命令，以最大化并行度同时避免耗尽本机资源。

### 7.2 深度研究

内置 `/deep-research` 工作流会扇出网页搜索、获取来源、对来源中的主张做对抗式验证，并综合出一份带引用的报告。

这类研究不只适用于网页搜索，例如：
- 从 Slack 中的上下文汇总一份状态报告
- 通过深入探索代码库研究某个功能是如何工作的

### 7.3 深度验证

如果有一份报告并希望检查其中引用的每一个事实性主张和来源：
1. 让一个智能体识别所有事实性主张
2. 为每条主张派生子智能体做详细检查
3. 用验证智能体检查来源子智能体，确保来源质量足够高

### 7.4 排序

有一组条目希望根据定性标准排序时（例如支持工单按 bug 严重程度排序），如果在一个提示词里排序 1000 多行，质量会下降，也放不进上下文。

更好的方式：
- 运行**锦标赛**（两两比较智能体组成的流水线）
- 并行分桶排序再合并

比较判断通常比绝对打分更可靠。每次比较都是一个独立智能体，确定性的循环负责维护赛程，只有当前运行顺序留在上下文中。

### 7.5 记忆与规则遵循

**正向：规则验证**
如果有一组规则（即使放进 CLAUDE.md 仍经常漏掉），可以创建工作流，列出必须由验证智能体检查的规则，每条规则一个验证智能体。创建一个怀疑者人格的子智能体来复查规则是否合理，有助于避免过多误报。

**反向：规则提炼**
挖掘最近的会话和代码评审评论，找出反复做出的修正；用并行智能体聚类；对每个候选规则做对抗式验证（“这条规则是否本可以防止一个真实错误”）；然后把存活下来的规则提炼回 CLAUDE.md。

### 7.6 根因调查

调试最有效的方法是提出多个独立假设并逐一测试。但如果只用一个上下文窗口，Claude 可能陷入自我偏好偏差。

工作流可以通过结构设计防止这一点：
1. 派生多个智能体，从**互不重叠的证据**中生成假设（日志、文件、数据分别设置智能体）
2. 每个假设面对一组验证者和反驳者

这不只适用于代码。工作流也可用于销售（“为什么三月销售额下降了”）、数据工程（“为什么这条流水线失败了”）、以及任何事后复盘。

### 7.7 大规模分流

每个团队都有支持队列、bug 报告或人类无法完全处理的积压事项。

分流工作流会对每个条目分类、与已追踪事项去重、并采取行动（尝试修复或升级给人类用户）。

**关键模式——隔离区：** 读取不可信公开内容的智能体被禁止执行高权限动作；高权限动作由负责根据这些信息行动的智能体来完成。

把分流工作流与 `/loop` 配对，可以让 Claude 持续执行这类任务。

### 7.8 探索与品味

在探索不同解决方案时，工作流很有用，尤其是设计或命名这类依赖品味、又受益于评分标准的任务。可以让 Claude 探索一批方案，并给评审智能体一套“什么才算好方案”的评分标准。当评审智能体认为标准已满足时，任务完成。方案也可通过锦标赛来排序或选择。

### 7.9 Evals

可以为特定任务运行轻量级 evals：在 worktree 中派生独立智能体，然后派生比较智能体，根据评分标准比较并打分具体输出。例如，根据特定条件评估并改进创建的某个 Skill。

### 7.10 模型与智能路由

创建针对任务调优过的分类器智能体，由它决定使用哪个模型。当任务会涉及许多工具调用，并且执行前的研究可以帮助识别最适合的模型时，这会很有用。

例如，“解释 auth 模块如何工作”的最佳模型，取决于 auth 模块里有多少文件以及代码库的形态。分类器智能体可以先做研究，再根据预期复杂度路由到 Sonnet 或 Opus。

---

## 八、避坑指南与最佳实践

### 8.1 什么时候不该使用

工作流仍然很新。虽然在很多场景能带来超额收益，但**不是每个任务都需要它**，且可能显著增加 token 消耗。

更适合的做法是，用工作流创造性地推动 Claude Code 去做过去难以做到的事情。对常规编码任务，先问自己：**它真的需要更多计算吗？** 例如，多数传统编码任务并不需要 5 个评审者组成的小组。

### 8.2 成本控制

- workflow 中每个 agent 默认使用会话模型，大运行前先 `/model` 确认
- 可让 Claude 把不需要最强模型的阶段换成小模型
- 一次 workflow 会 spawn 大量 agent，单次运行比对话里做同一任务消耗更多 token

### 8.3 提示词建议

为动态工作流写详细提示词，并使用前面介绍的具体编排模式，通常会得到最好的结果。工作流不只适用于大型任务，也可以提示模型使用“快速工作流”，例如围绕某个假设做一次快速对抗式评审。

### 8.4 结合 /goal 和 /loop

当使用可以重复运行的工作流时（如分流、研究或验证），可以把它们与 `/loop` 配对，按固定间隔运行；再配合 `/goal` 设置硬性完成要求。

### 8.5 Token 使用预算

可以为动态工作流设置显式 token 预算，限制某个任务使用多少 token。可以像这样提示它：“使用 10k token”，这会设置上限。

### 8.6 保存和分享工作流

在工作流菜单里按 `s` 保存工作流。保存后可以：
- 提交到 `~/.claude/workflows`
- 通过 Skill 分发：把 JavaScript 工作流文件放进 skill 文件夹，并在 SKILL.md 中引用它们。为了获得更大灵活性，可以提示 Claude 把 Skill 里的工作流当作模板，而不是必须逐字运行的脚本

### 8.7 关闭方式（三选一）

1. `/config` 里关掉 Dynamic Workflows
2. `~/.claude/settings.json` 设置 `"disableWorkflows": true`
3. 环境变量 `CLAUDE_CODE_DISABLE_WORKFLOWS=1`

组织级可通过 managed settings 关闭。关闭后：bundled 命令不可用、workflow 词不再触发、ultracode 从 /effort 菜单移除。

### 8.8 注意事项

- 可随时从 `/workflows` 停止，不会丢失已完成的工作
- 运行计入方案的用量与速率限制

---

## 九、生态发展

Dynamic Workflows 的发布将对图形化编排软件（FastGPT、Dify）造成冲击，同时让非技术人员也能编写更强大的应用场景。

### 推荐生态项目

| 项目 | 地址 | 说明 |
|------|------|------|
| **多 Agent 编排实战手册** | [workflow-cookbook](https://github.com/AGI-is-going-to-arrive/workflow-cookbook) | 从零到一掌握全部 API，实战 7 个真实配方 |
| **可视化工具** | [claude-workflow-viz](https://github.com/democra-ai/claude-workflow-viz) | 将隐藏的执行数据变为直观图表 |
| **轻量级脚手架** | [agent-workflows](https://github.com/akakabrian/agent-workflows) | 无依赖、跨平台、纯 Python 的动态 Agent 工作流运行时 |
| **交互式调研报告** | [cc-dynamic-workflows](https://github.com/cclank/cc-dynamic-workflows) | 单页 HTML 报告，讲清定义、执行模型、API、案例 |

---

## 十、总结

Dynamic Workflows 的关键创新：

- **上下文卸载（Context Offloading）** — 计划留在代码里，不留上下文里
- **对抗三大失败模式** — 智能体偷懒、自我偏好偏差、目标漂移
- **六大编排模式** — 分类并执行、扇出并综合、对抗式验证、生成并过滤、锦标赛、循环直到完成
- **数百至上千个 Agent 的并行协作** — 真正的工程团队级并发
- **动态 vs 静态** — Claude 为当前任务即时编写运行框架，而非依赖通用预写编排
- **检查点恢复与长任务持续运行** — 中断可恢复，进度不丢失

> 工作流是一种扩展 Claude Code 的新方式。关于如何最好地使用它们，还有很多值得探索。
> —— Thariq Shihipar（Anthropic 技术团队）

> 未来的软件开发竞争，或许不再只是模型能力的竞争，而是 **Agent 编排能力**的竞争；未来最重要的资产，也许不再是 Prompt，而是 **Workflow**。
