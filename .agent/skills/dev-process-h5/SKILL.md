---
name: dev-process-h5
description: "H5 移动端设计开发规范 —— 预防：组件 store 订阅崩溃、图标名不存在、CSS 覆盖冲突、嵌套滚动、视口溢出、代理漏配。覆盖：scene/http_sse/static/src/h5/"
---

# H5 移动端设计开发规范

> 桌面端和 H5 共享 stores/api/hooks/components。H5 只覆盖布局壳和导航模式。

---

## 修改前快速检查

```
□ 新增/修改 H5 组件？→ 检查是否订阅了流式过程中会频繁更新的 store（companion-store 等）
□ 用了 Icon 组件？→ 打开 Icon.tsx 确认 IconName 类型里该图标名存在
□ 新增 CSS 规则？→ 检查是否和组件专属 CSS 冲突（不要在两处定义同一个类）
□ 新增容器？→ 检查是否有嵌套 overflow:auto（同方向只允许一个滚动容器）
□ 改了 API 路径？→ 检查 vite.config.ts proxy 是否覆盖了该路径
□ 根容器用了 100vw？→ 改为 100%
```

---

## 规则 1：H5 组件不订阅流式中更新的 store

**原因：** CollapsibleInput 订阅 `useCompanionStore` 导致流式消息过程中白屏崩溃。companion store 在 SSE 事件中频繁更新，触发组件重渲染，与 Motion AnimatePresence 的状态切换冲突。

**检测：** grep 新增 H5 组件中的 `useCompanionStore`、`useChatStore` 等会在流式过程中更新的 store。如果组件通过 AnimatePresence 频繁 mount/unmount，改为本地状态或通过 props 传递。

**案例：** `CollapsibleInput.tsx` 原本订阅 `useCompanionStore((s) => s.mood)` → 改为本地 `useState` 循环切换表情。

---

## 规则 2：Icon name 必须对照 Icon.tsx 的 IconName 类型

**原因：** `square` 和 `chevronRight` 不是合法的图标名，导致按钮不可见。Icon.tsx 的 `IconName` 类型是所有合法名称的唯一来源。

**检测：** 每次使用 `<Icon name="..." />` 之前，确认该字符串在 `Icon.tsx` 的 `type IconName =` 联合类型中存在。

**常见错误：** camelCase（`chevronRight`）→ 实际是 kebab-case（`chevron-right`）

---

## 规则 3：组件 CSS 是唯一样式源

**原因：** h5.css 和 SettingsPage.css 对 `.h5-settings-row` 的 padding/font-size 有不同定义，产生冲突。组件专属类只在组件 CSS 文件中定义，全局覆盖文件（h5.css）只覆盖共享的桌面端组件样式。

**检测：** grep 同一个 CSS class 是否在 h5.css 和任意组件 CSS 文件中都出现非共享选择器。如果是，删除 h5.css 中的版本。

---

## 规则 4：禁止同方向嵌套 overflow:auto

**原因：** .h5-content 设 `overflow-y: auto`，.chat-container 也设 `overflow-y: auto`，产生嵌套滚动。移动端表现为滚动卡顿或无法滚动。

**检测：** 检查组件树的滚动链：只有最内层需要滚动的容器设 `overflow-y: auto`，所有祖先设 `overflow: hidden`。

**正确模式：** .h5-page（overflow: hidden） → .chat-container（overflow-y: auto，唯一滚动容器）

---

## 规则 5：Vite proxy 必须覆盖所有 API 路径

**原因：** vite.config.ts 只配了 6 个路径，但 api/client.ts 实际请求 15+ 个路径（/personas、/capabilities、/connectors 等）。漏配的路径全部 404。

**检测：** 修改 api/client.ts 后，grep 所有 `fetch(` 调用的路径，确保 vite.config.ts proxy 中每个前缀都有覆盖。

---

## 规则 6：根容器禁止 100vw

**原因：** `100vw` 包含滚动条宽度，在移动端/设备模式下导致横向溢出。

**修复：** `.app-layout { width: 100vw }` → `width: 100%`

---

## 规则 7：移动端输入框控件最小化

**原因：** 桌面端 ChatInput 有 6 个控件（技能/更多/模型/录音/文件/发送），在 430px 宽度下拥挤不堪。

**方案：** ChatInput 接受 `compact` prop。H5 端传入 `compact`，所有辅助控件折叠到单个 "+" 弹窗中，主界面只保留发送按钮。

---

## 规则 8：保持简洁克制

**原因：** 手机屏幕空间珍贵。每个像素都要挣得自己的位置。

- Header 只保留必要控件（主题切换），伴随便携精灵隐藏
- 输入框常态收起为 FAB 浮标，点击唤醒
- 不添加纯装饰性动画（脉冲环等）
- CSS 动画包裹在 `@media (prefers-reduced-motion: no-preference)` 中
