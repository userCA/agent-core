# H5 前端引入开源组件库方案

## 现状

| 项目 | 数值 |
|------|------|
| 自定义组件 | 32 个 `.tsx` + 20 个 `.css` |
| UI 依赖 | 零。仅 `react` + `zustand` + `motion` + `marked` |
| 按钮实现 | 纯 CSS 类 `.btn` / `.btn-primary`，无组件封装 |
| 图标实现 | 手写 `Icon.tsx`（50+ SVG 内联） |
| 折叠/手风琴 | 5 个页面各自手写 Set toggle 模式 |
| 主题 | 一个 `tokens.css`，约 20 个 CSS 变量 |

## 为什么需要改

1. **32 个手写组件全是负债**。Button、Icon、Loading、EmptyState、Modal、Toast —— 开源库 `npm install` 解决的事，现有上千行手写代码需要维护
2. **无障碍性缺失**。开源库内置 focus trap、keyboard nav、ARIA、屏幕阅读器支持。手写代码里 `aria-expanded` 只出现了 1 次
3. **5 种折叠面板实现**。ConnectorsPage、ExpertsPage、KnowledgePage、ChannelsPage、SkillsPage 各自手写 Set toggle 模式，不一致且难维护
4. **无主题系统**。暗色模式/多主题需从头造轮子
5. **无 i18n 基础设施**。组件库通常内置 `LocaleProvider`

## 推荐方案：Radix UI Primitives

**选型理由：**

- 无样式 headless 组件 —— 不绑架 CSS，继续用现有变量体系
- 完美内置无障碍 —— 焦点管理、键盘导航、ARIA 全自动
- 增量迁移 —— 每个 primitive 独立发包，用哪个装哪个
- 包体积小 —— 不用的不引入

### 备选对比

| 方案 | 优势 | 不选原因 |
|------|------|---------|
| shadcn/ui | 基于 Radix，样式精美 | 需要引入 Tailwind CSS |
| Ant Design Mobile | 专为 H5，组件齐全 | 包体积大，风格固定，和现有视觉冲突大 |
| Vant | 轻量 H5 组件 | 和现有 React 技术栈不匹配（Vue 优先） |

## 迁移路径

### Phase 1：替换最乱的 3 个手写模式（收益最大）

```
npm install @radix-ui/react-collapsible @radix-ui/react-alert-dialog @radix-ui/react-toast
```

**折叠面板 → `@radix-ui/react-collapsible`**

当前 5 种手写模式，统一为：

```tsx
import * as Collapsible from '@radix-ui/react-collapsible';

<Collapsible.Root open={open} onOpenChange={setOpen}>
  <Collapsible.Trigger asChild>
    <button className="evo-trigger" aria-label="展开">
      <Icon name="chevron-down" />
      Evolution
    </button>
  </Collapsible.Trigger>
  <Collapsible.Content>
    {/* 内容 */}
  </Collapsible.Content>
</Collapsible.Root>
```

涉及文件：`ConnectorsPage`、`ExpertsPage`、`KnowledgePage`、`ChannelsPage`、`SkillsPage`（工具卡片）、`EvolutionPanel`

**确认弹窗 → `@radix-ui/react-alert-dialog`**

替换手写的 `ConfirmDialog` 组件 + `useConfirmStore`：

```tsx
import * as AlertDialog from '@radix-ui/react-alert-dialog';

<AlertDialog.Root>
  <AlertDialog.Trigger asChild>
    <button className="btn btn-danger">Reject</button>
  </AlertDialog.Trigger>
  <AlertDialog.Portal>
    <AlertDialog.Overlay className="dialog-overlay" />
    <AlertDialog.Content className="dialog-content">
      <AlertDialog.Title>确认拒绝</AlertDialog.Title>
      <AlertDialog.Description>此操作不可撤销</AlertDialog.Description>
      <AlertDialog.Cancel asChild><button className="btn">取消</button></AlertDialog.Cancel>
      <AlertDialog.Action asChild><button className="btn btn-danger">确认</button></AlertDialog.Action>
    </AlertDialog.Content>
  </AlertDialog.Portal>
</AlertDialog.Root>
```

**Toast → `@radix-ui/react-toast`**

替换手写的 `Toast` 组件 + `useToastStore`：

```tsx
import * as Toast from '@radix-ui/react-toast';

<Toast.Provider>
  <Toast.Root className="toast-root" duration={4000}>
    <Toast.Title>操作成功</Toast.Title>
    <Toast.Description>Proposal accepted</Toast.Description>
  </Toast.Root>
  <Toast.Viewport className="toast-viewport" />
</Toast.Provider>
```

### Phase 1.5：图标库替换

```
npm install lucide-react
```

用 `lucide-react` 替换手写的 50+ SVG `Icon.tsx`。lucide 提供 1000+ 图标，按需引入，tree-shakable。

```tsx
// 旧
<Icon name="check" size={16} />
// 新
import { Check, ChevronDown, Settings, X } from 'lucide-react';
<Check size={16} />
```

### Phase 2：基础交互组件

```
npm install @radix-ui/react-toggle @radix-ui/react-switch @radix-ui/react-tooltip
```

- Toggle → 替换 `.skill-toggle` 开关
- Switch → 替换手写的 toggle 样式
- Tooltip → 替换手写的 title 属性

### Phase 3（可选）：表单 + 选择

```
npm install @radix-ui/react-form @radix-ui/react-select @radix-ui/react-popover
```

## 不改什么

| 保留项 | 理由 |
|--------|------|
| Zustand 状态管理 | 已在用，没问题，和 Radix 不冲突 |
| motion 动画库 | 已在用，Radix 组件可配合 `asChild` 使用 |
| 页面布局 CSS | `.page` / `.page-header` / `.card-grid` 保留 |
| 颜色变量体系 | `tokens.css` 保留，Radix 组件通过 className 使用 |
| EvolutionPanel diff/光环 | 业务特有，无开源等价物 |
| Markdown 渲染 | `marked` + `dompurify` 保留 |

## 实施顺序

| 步骤 | 内容 | 影响范围 | 预估时间 |
|------|------|---------|---------|
| 1 | 装 `@radix-ui/react-collapsible`，替换 5 个页面的折叠模式 | 6 文件 | 1h |
| 2 | 装 `@radix-ui/react-alert-dialog`，替换 `ConfirmDialog` | 所有使用处 | 30min |
| 3 | 装 `@radix-ui/react-toast`，替换 `Toast` | 所有使用处 | 30min |
| 4 | 装 `lucide-react`，替换 `Icon.tsx` | 所有使用处 | 1h |
| 5 | 构建验证 + 测试 | - | 30min |

**总投入约 3.5h，消除 5 种折叠实现 + 手写 Icon/Toast/Confirm 的维护负担。**
