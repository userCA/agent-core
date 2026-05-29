---
name: dev-process-frontend
description: "前端开发流程规范（TypeScript/React）—— dev-process-optimizer 的子 skill。预防：数据源/显示源混淆、中间状态破坏、回归连锁反应、边缘问题过度优化、代码替换边界错误。覆盖：scene/http_sse/static/src/ 的 components/hooks/stores/utils。"
---

# 前端开发流程规范（React/TypeScript）

> 子 skill，架构/跨层问题先看 `dev-process-optimizer`。

防止重复犯错。每条规则都源于真实 bug，全部案例来自 `scene/http_sse/static/src/`。

---

## 修改前快速检查

```
□ 先画数据流图 —— 哪个是数据源？哪个是显示层？
□ 列出所有依赖你要修改的变量的其他状态变量
□ 会不会影响：纯文本？think+文本？think+工具？多轮对话？四种全测。
□ 如果修复需要 >20 行新状态逻辑：不修的话最坏结果是什么？
□ old_string 的边界是否完整（完整代码块，包含闭合括号/标签）？
```

---

## 规则 1：区分数据源和显示源

**最重要的前端规则。** 这条在 2026-05-14 一天内引发了 3 次回归。

**数据流管道：**
```
currentText（原始，累积所有 delta）
  ├─→ typeQueue（逐个字符，原始文本）
  │     └─→ displayedText（原始，打字机累积用）
  │           └─→ getDisplayableText(displayedText) → DOM（过滤后）
  └─→ extractThinkSteps(currentText) → StepsPanel（需要原始 think 标签）
```

**核心规则：** `getDisplayableText` 是纯渲染层过滤器。它在 DOM 显示前剥离 `<think>` 标签。绝对不能用于过滤进入打字机队列之前的数据。如果在数据层过滤，`extractThinkSteps`（从 `currentText` 读取）也许还能工作，但过滤器下游的其他消费者全坏了。

**真实案例（2026-05-14）：** 为了防止 `<think>` 在打字机中闪现，引入了 `lastQueuedDisplayable` —— 只 enqueue "可显示"的字符。这过滤了打字机输入。结果：`displayedText` 不再包含 `<think>` 标签 → `extractThinkSteps()`（原本从 `displayedText` 读取）找不到 think 块 → 思考内容消失。

**修复过程：**
1. 把 `extractThinkSteps` 改为从 `currentText`（原始文本）提取 → 思考内容恢复
2. 完全移除 `lastQueuedDisplayable` → 回到原始文本 enqueue

**检查：** 每个文本转换必须分类为"数据转换"（影响所有消费者）或"显示过滤"（只影响一个渲染路径）。显示过滤放在 DOM 之前的最后一步。

---

## 规则 2：中间状态 —— 每新增一个状态变量必须验证和所有依赖的同步

**模式：** 新增一个派生/镜像自另一个状态的状态变量，同步负担立增。四个互相依赖的变量 = 组合爆炸的 bug 空间。

**真实案例（2026-05-14）：** think 标签修复引入了 `lastQueuedDisplayable` 作为第四个状态变量，和 `displayedText`、`currentText`、`typeQueue` 并存。当 `<think>` 块跨多个 delta 到达时，部分 `<think` 标签被 enqueue（因为 `getDisplayableText` 还没看到 `>`），`displayedText` 累积了 `<think`，但 `lastQueuedDisplayable` 追踪的位置不同 → 同步崩溃 → 最终答案被截断。

**规则：** 新增派生状态变量前，先问：
1. 能否从现有状态计算得出？（派生值 → 用 `useMemo` 或读时计算）
2. 如果必须存储：列出所有会修改它或被它修改的其他变量
3. 写出同步不变量："每次 enqueue 后，X 必须等于 f(Y)"

---

## 规则 3：回归测试矩阵 —— 每次必测四种场景

**模式：** 只测自己修的那个场景，是回归的根本原因。

**真实案例（2026-05-14）：** 三轮连锁反应：
1. 修复 `<think>` 闪现 → 思考内容丢失（只测了闪现场景）
2. 修复思考内容丢失 → 最终答案不输出（只测了思考场景）
3. 修复最终答案 → 全部正常（四种全测了）

**矩阵 —— 任何涉及 streaming/typewriter/think/hitl 的修改后：**
```
□ 纯文本（无 think、无工具）→ "Hello" → "Hi there!"
□ Think + 文本（有 think 块后有回答）→ <think>...</think> + 回答可见
□ Think + 工具（有 think 块后有工具调用）→ <think>...</think> + 工具步骤可见
□ 多轮对话（第二轮正常继续）→ 先问一个问题，再追问
```

**检查：** 如果改动涉及 `useTypewriter`、`think.ts`、`chat-store.ts`、`StreamingMessage.tsx`，四种场景必须手动全部跑一遍。不是"应该没问题"——实际验证。

---

## 规则 4：边缘问题性价比评估 —— 代价 vs 后果

**模式：** 不是所有 bug 都值得修。为了修一个视觉瑕疵引入复杂方案，可能摧毁核心功能。

**真实案例（2026-05-14）：** `<think>` 字符在打字机过程中闪现 ~100ms（视觉瑕疵）→ 50+ 行的 `lastQueuedDisplayable` 同步逻辑 → 最终答案完全消失（灾难性）。

**评估框架：**
| 修复复杂度 | Bug 严重程度 | 决策 |
|---|---|---|
| <10 行 | 视觉瑕疵（闪现/抖动） | 修 |
| 10-30 行 | 视觉瑕疵 | 考虑：有没有更简单的方法？ |
| >30 行 | 视觉瑕疵 | 不修。接受瑕疵。 |
| 任意 | 核心功能损坏（答案丢失、崩溃） | 修，四种场景全测 |

**检查：** 在实现一个需要新增状态管理的视觉修复之前，大声说出来："如果这个修复失败，最坏的结果是___。"如果答案包含"整个答案消失"或"应用崩溃"，不修。

---

## 规则 5：代码替换 —— 完整块边界

**模式：** 替换代码块时 `old_string` 如果没包含闭合括号/标签，会产生语法错误。

**真实案例（2026-05-14）：** 替换 `} else if { ... }` 时漏掉了闭合的 `}`，产生 `enqueueType(data.text); else if`。

**规则：** `old_string` 必须：
1. 从行边界开始（语句开头）
2. 以完整块闭合结束（`}` / `)` / `;`）
3. 包含内部所有配对的括号/花括号

**检查：** 替换后立刻检查 IDE diagnostics / linter。不要靠肉眼审查。

---

## 规则 6：流式数据流 —— 唯一真相源

**模式：** 流式管道有多个消费者读取同一原始文本。每个消费者必须从正确的源头读取。

**当前架构（截至 2026-05-26）：**

```
SSE text delta 到达
  → chat-store.appendText(delta)  // 累积 currentText（原始）
  → typewriter.enqueue(delta)     // 原始字符入打字机队列

打字机循环（useTypewriter.ts）：
  → fullTextRef 累积原始字符
  → onFlush(fullText, isActive)   // 传递原始文本给渲染层

StreamingMessage 渲染：
  → extractThinkSteps(props.rawText)     // 读原始文本 → StepsPanel（需要 <think>）
  → getDisplayableText(props.rawText)    // 读原始文本 → 剥离 <think> → DOM 文本
```

**核心不变量：** `currentText` 是唯一真相源。`getDisplayableText` 和 `extractThinkSteps` 都从它读取。谁也不修改它。打字机接收原始字符，渲染时过滤器在最后一刻剥离 think 标签。

**检查：** 新增文本转换前，明确：它从 `currentText` 读吗？它会写入新的过滤版本吗？如果写入，哪些消费者应该用过滤版、哪些应该用原始版？

---

## 规则 7：Zustand Store —— 聊天状态和 UI 状态分离

**模式：** 把消息数据和 UI 临时状态混在一起，会导致 reset bug 和不必要的重渲染。

**当前拆分：**
- `chat-store.ts` —— 消息、步骤、流式状态、currentText、thinkingText、widgets/audios、usage。跨渲染持久化。
- `ui-store.ts` —— 面板折叠、弹窗状态、输入焦点。临时 UI 状态。
- `session-store.ts` —— Session ID、连接状态。

**检查：** 新增字段前，问自己："这描述的是用户看到了什么（聊天内容），还是怎么展示（UI 装饰）？" 内容 → chat-store。装饰 → ui-store。

---

## 规则 8：打字机 —— 不在 enqueue 前预过滤

**模式：** 打字机队列必须接收原始文本。过滤在渲染时通过 `getDisplayableText` 完成。

**为什么：** 如果在 enqueue 前过滤，打字机的 `fullTextRef` 累积的是过滤后文本。那么 `extractThinkSteps`（从 `currentText` 读原始文本）和打字机显示（从 `fullTextRef` 显示过滤文本）就会分化。

**真实案例（2026-05-14）：** `lastQueuedDisplayable` 在 enqueue 前过滤字符 → `fullTextRef` 和 `currentText` 分化 → think 提取失败。

**检查：** 传给 `typewriter.enqueue()` 的唯一参数应该是原始 delta 文本。永远不要传 `getDisplayableText(delta)` 或任何过滤变体。

---

## 规则 9：流式渲染 —— 逐字显示期间不做昂贵格式转换

**模式：** 在打字机/流式输出过程中调用 `marked.parse`、`DOMPurify.sanitize`、或任何 O(n) 的格式转换，会导致：
1. 每帧高 CPU 占用（帧率下降）
2. 原始文本 ↔ 转换后 HTML 结构差异造成的视觉跳变
3. 队列空/非空切换时的反复重渲染

**真实案例（2026-05-27）：** `StreamingMessage` 的 `handleFlush` 在 `isActive=true` 时用 raw text（`<br>`），`isActive=false` 时用 `renderMarkdown()`（完整 HTML）。typewriter 队列短暂为空时（事件间隔 > 45ms），就会从 raw text 切到 Markdown 再切回来。`marked.parse` + `DOMPurify.sanitize` 每几百毫秒执行一次，造成明显帧率下降和视觉"闪现"。

**修复：** 流式过程中始终使用轻量 raw text 渲染。昂贵的格式转换只在流结束后执行一次（由 `MessageBubble` 负责最终 Markdown 渲染）。

**检查：** `onFlush` 回调中是否有条件分支调用 `marked.parse`、`hljs.highlight`、`JSON.parse` 等？如果有，把条件改为 `!isStreaming`（流结束后一次性格式化），或把格式化移到最终消息组件。

---

## 规则 10：SSE 批处理 —— 创建新 UI 元素后让出渲染帧

**模式：** `reader.read()` 一次返回的 TCP chunk 可能包含多个 SSE 事件。`parseSSEStream` 的 `for` 循环将它们全部同步 yield，`_runStream` 的 `for await` 在同一微任务内调用多次 `processEvent()`。React 18 自动批处理将所有 zustand store 更新合并成一次渲染——用户看到的是一瞬间出现的完整结果。

**真实案例（2026-05-27）：** `thinking_delta` 事件全部在同一个 chunk 中到达 → `processEvent` 创建 step + 多次 `updateStep` → 所有更新被 React 批处理 → 思考步骤以 `done` 状态闪现，中间没有 `running` 状态的渲染帧。

**修复：** 在 `_runStream` 中，处理会创建新 UI 元素的事件后 `await setTimeout(0)`：
```typescript
for await (const evt of gen) {
    processEvent(evt);
    if (evt.event === 'thinking_delta' || evt.event === 'tool_start') {
        await new Promise((r) => setTimeout(r, 0));
    }
}
```
`text_delta` 不需要（typewriter 已有自己的节奏）。

**检查：** 新增 SSE 事件类型 → 如果它创建新的 UI 组件/步骤，加入上面的让出列表。

---

## 规则 11：Store 变量消费者检查 —— 写入的必须被渲染

**模式：** zustand store 中新增字段 → `appendXxx()` action 写入 → 但没有任何组件 `useChatStore((s) => s.xxx)` 读取它。数据在后台沉默累积，用户看不到。

**真实案例（2026-05-27）：** `thinkingText` 字段存储 `thinking_delta` 事件内容，`appendThinking()` 不断追加。但 `StreamingMessage` 从未读取 `thinkingText`——只在最终消息收割时做了兜底 `finalState.currentText || finalState.thinkingText`。所有 thinking_delta 内容在流式过程中对用户不可见。

**修复：** 让 `processEvent` 中首个 `thinking_delta` 创建 running 步骤，后续流式更新 detail。

**检测方法：** 新增 store 字段后回答两个问题：
1. 哪里写入？（grep `setXxx` / `appendXxx` 调用点）
2. 哪里读取？（grep `useChatStore((s) => s.xxx)` 或 `getState().xxx`）
如果问题 2 为空或只在 teardown 处用，它就是死字段。

---

## 规则 12：按钮不嵌套交互元素 —— 用 div 容器 + 同级 button

**模式：** 在 `<button>` 内部放带 `onClick` 的子元素（`<span onClick>`、`<a>`、另一个 `<button>`）会导致子元素点击不触发或行为异常。HTML 规范禁止 `<button>` 包含交互式内容。

**真实案例（2026-05-29）：** Session 列表的删除按钮放在 `<button className="session-item">` 内部作为 `<span className="session-delete" onClick={...}>`，`stopPropagation` 无效，点击 × 始终触发外层 `handleSwitch` 而非删除。

**规则：** 需要一块区域内有两个独立点击目标时：
```tsx
// 错误：嵌套
<button onClick={handleMain}>
  内容
  <span onClick={handleDelete}>×</span>   // 不会触发
</button>

// 正确：div 容器 + 同级 button
<div className="container">
  <button className="main-area" onClick={handleMain}>内容</button>
  <button className="delete-btn" onClick={handleDelete}>×</button>
</div>
```

**检查：** 新增 UI 中有两个不同作用点击区域时，问自己：它们在同一 `<button>` 内部吗？如果是，改为 `<div>` + 同级 `<button>`。

---

## 规则 13：所有输入框必须有统一的 focus 样式

**模式：** 新增页面或组件的 `<input>`、`<textarea>`、`<select>` 只改了 `border-color` 但没有 `box-shadow` 光圈，与已有的 `.chat-textarea` 不一致。用户在不同页面间切换时感受到焦点反馈不统一。

**真实案例（2026-05-29）：** 技能/连接器页面中 `.page-search input` 和 `.form-field input:focus` 缺少 `box-shadow: 0 0 0 3px var(--focus-ring)` 和 `focus-within` 处理，导致焦点视觉反馈弱于聊天页。

**统一 focus 样式模板：**
```css
/* 独立输入框容器 */
.input-wrapper {
    border: 1px solid var(--hairline);
    border-radius: var(--radius-sm);
    background: var(--surface-soft);
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.input-wrapper:focus-within {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--focus-ring);
}
.input-wrapper input { border: none; background: transparent; outline: none; }

/* 独立表单输入框 */
.form-field input:focus,
.form-field select:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--focus-ring);
}
```

**检查：** 新增任何 `<input>` / `<textarea>` / `<select>` 后，验证其 `:focus` 样式是否有 `border-color: var(--accent)` + `box-shadow: 0 0 0 3px var(--focus-ring)`。

---

## 修改后验证

```
□ 四种场景矩阵全通过（纯文本 / think+文本 / think+工具 / 多轮对话）
□ 没有新增镜像已有变量的状态变量
□ 数据流从原始源 → 渲染时过滤（不是管道中途过滤）
□ Linter/TypeScript：无新诊断
□ git diff 已审查 —— 无意外改动的相邻代码
□ 如果涉及 think.ts 或 useTypewriter.ts：测试了不完整 <think> 标签（流式边界情况）
□ 如果涉及 StreamingMessage：确认流式期间没有调用 marked.parse / DOMPurify
□ 新增输入元素：确认 :focus 有统一的 border-color + box-shadow 光圈
```

```
□ 四种场景矩阵全通过（纯文本 / think+文本 / think+工具 / 多轮对话）
□ 没有新增镜像已有变量的状态变量
□ 数据流从原始源 → 渲染时过滤（不是管道中途过滤）
□ Linter/TypeScript：无新诊断
□ git diff 已审查 —— 无意外改动的相邻代码
□ 如果涉及 think.ts 或 useTypewriter.ts：测试了不完整 <think> 标签（流式边界情况）
□ 如果涉及 StreamingMessage：确认流式期间没有调用 marked.parse / DOMPurify
```
