# 13 — 形象演化与专属媒体

## 当前缺口

bond 成长系统 (§06) 解锁的是行为层内容（慢眨眼/翻肚皮/踩奶），猫的 ASCII 形象不
随成长改变。一只 STRANGER 橘猫和一只 SOULMATE 橘猫长得一模一样。

## 一、形象演化 — 低成本、高感知

### 演化阶段

```
幼年期 (STRANGER)     →  成长期 (ACQUAINTANCE)  →  成熟期 (FRIEND+)
   小猫形态                   换毛/变色                  稳定形态 + 专属印记
```

### 每阶段视觉变化

| 阶段 | 体型 | 眼睛 | 配饰 | 特效 |
|------|------|------|------|------|
| STRANGER | 缩小版精灵 (80% 大小) | 圆眼比例高 | none | — |
| ACQUAINTANCE | 正常大小 | 品种默认眼 | 基础配饰解锁 | — |
| FRIEND | 正常 | 眼睛偶尔 `♥` (bond高了自然流露) | 中级配饰 | — |
| CLOSE | 微胖/蓬松 (养得好) | 稳定品种眼 | 高级配饰 | 名字轻微发光 |
| SOULMATE | 独特标记 (品种专属) | 专属眼神 | 星光项圈 | 永久粒子特效 |

### 幼年期 (kitten) 精灵

只改一行: 渲染时根据 bond level 缩放。幼年期使用 kitten 变体帧:

```
成猫橘猫:              幼猫橘猫 (STRANGER, 缩小 + 圆润):
   /\_/\                 /\_/\  
  ( o   o )             (·   ·)     ← 眯眯眼更圆
  (  ω   )              ( ω )       ← 嘴更小
  (")_(")               (")_(")     ← 等比例缩小
   橘子                  小橘子       ← 名字可能加 "小" 前缀
```

### 品种专属 SOULMATE 印记

到达 SOULMATE 后，每个品种获得一个**永久视觉标记**——用户看了就知道这是老伙计:

| 品种 | SOULMATE 印记 |
|------|-------------|
| 橘猫 | 嘴角永远上扬 `ω→▽` (一直很开心) |
| 奶牛 | 额头出现小星星 `＊` (永远兴奋) |
| 三花 | 异色眼眶消失→双眼同色 (终于卸下防备) |
| 暹罗 | 嘴型 `▽→ω` (从挑剔变成了温和) |
| 黑猫 | 眼睛从 `◉` 变为 `◉✦` (星光眼, 不再隐藏) |
| 布偶 | 长毛更长 `~(")___(")~` 变 `~(")~~~~(")~` (幸福的毛更蓬了) |
| 折耳 | 耳朵微微抬起 `__/\__` → `~/\\~` (不再那么害怕了) |

### 演化实现

```python
# sprite 渲染时多一个参数
def render_sprite(bones, bond_level, frame):
    if bond_level == BOND_STRANGER:
        body = KITTEN_SPRITES[bones.breed][frame]  # 幼年帧
    elif bond_level >= BOND_SOULMATE:
        body = SOULMATE_SPRITES[bones.breed][frame]  # 带印记帧
    else:
        body = ADULT_SPRITES[bones.breed][frame]     # 成年帧
    return body
```

前端成本: **0 行新增**。渲染管线不变，帧池多 2 套。

---

## 二、生图/生视频 — 中高成本、极高感知

### 2.1 我们有什么 (生成 prompt 的输入)

每只咪兔的完整视觉描述可由已有数据组装，无需额外存储:

```python
def compose_visual_prompt(bones, soul, milestones, bond_level) -> str:
    """从已有数据组装生图 prompt."""
    breed = BREED_PROFILES[bones.breed]
    
    prompt = f"""A cute {breed.display_name} cat character in anime/chibi style.
    
Physical traits:
- Breed: {breed.display_name} ({breed.physical_desc})
- Eyes: {EYE_DESC[bones.eye]} ({EYE_NAME[bones.eye]})
- Ears: {EAR_DESC[bones.ear]}
- Color palette: {COLOR_DESC[bones.color]}
- Body type: {breed.body_type}
- Special: {"shiny / sparkle particles around body" if bones.shiny else "normal fur"}

Accessories:
- Hat: {HAT_DESC.get(bones.hat, "none")}
- Accent: {ACCENT_DESC.get(bones.accent, "none")}
- SOULMATE mark: {SOULMATE_DESC.get(bones.breed, "") if bond_level >= 4 else ""}

Personality:
- {soul.personality}
- Bond level: {BOND_NAME[bond_level]}
- Style: {compute_style(observer).display_name}

Memories:
- First meeting: {milestones.get('first_meeting')}
- Favorite topic: {compute_top_topic(observer)}
- Total conversations: {observer.prompt_count}

Style: soft cel shading, clean lines, kawaii, white background, full body, 
looking at viewer, gentle smile, suitable for profile picture.
"""
    return prompt
```

prompt 中的每个字段都已经存在于现有系统中——只是从未组合成一个生图 prompt。

### 2.2 触发时机

| 时机 | 产出 | 成本 | 价值 |
|------|------|:--:|:--:|
| hatch 首次孵化 | **咪兔出生照** (1 张图) | 低 | 极高 — 第一天 hook |
| BOND 升级 (每次) | **成长记录照** (共 4 张) | 中 | 高 — 成长相册 |
| SOULMATE 达成 | **专属全家福** (1 张精图) | 低 | 极高 — 终极奖励 |
| 周年纪念 | **年度回顾视频** (可选) | 高 | 中 — 仪式感 |
| 用户主动触发 | `/buddy portrait` | 低 | 中 — 可分享 |

### 2.3 视频生成的替代方案

直接生视频成本高/质量不稳定。更好的方案:

**幻灯片视频**: 已有图片 + 文字 + milestone 时间轴 + 轻音乐
→ 用 ffmpeg/模板生成, 不调 AI, 成本≈零。

**帧动画拼接**: 同一只猫的 6 个 idle 帧连续放大渲染
→ 用 CSS/Canvas, 前端本地完成, 零成本。

### 2.4 实现分层

```
Layer 1 (低垂果实):
  ├── compose_visual_prompt() → 纯字符串拼装, ~30 行
  ├── ASCII 帧 → PNG 截图 (前端 Canvas 截图, 零成本)
  └── 成长相册 → milestone 时间线 + 已有截图

Layer 2 (需要 API):
  ├── 生图 API (OpenAI DALL-E / Stability / Replicate)
  │   └── 按需触发, 不自动生成 (成本控制)
  └── 图片缓存 (同 prompt 不重复生成, hash prompt→cache)

Layer 3 (有余力):
  └── 视频生成 (用 Layer 1 的图片拼成幻灯片即可)
```

### 2.5 成本控制

| 策略 | 说明 |
|------|------|
| **按需生成** | 不自动, 用户主动触发或里程碑触发时才调 API |
| **prompt 去重** | hash(prompt) → 如果已生成过, 用缓存 |
| **降级方案** | API 不可用时 → 前端渲染放大的 ASCII 精灵 + CSS 渐变背景 |
| **每用户上限** | 5 张/月 (避免滥用) |
| **共享成本** | 同品种+同配饰的猫 → 基础形象可复用 (换色即可) |

---

## 三、这些有价值吗？

### 形象演化 — ✅ 应该加

```
投入: 2 套精灵帧 (kitten + soulmate, 每品种 ~10 行 ASCII)
      渲染时多 1 行 bond_level 判断
感知: "我的猫长大了" — 比解锁一个气泡强烈 10 倍
时机: STRANGER→ACQUAINTANCE 的 kitten 形态让用户第一天就感知到变化
```

### 生图 — ✅ 有价值但按需

```
投入: compose_visual_prompt() ~30 行 + 接入一个生图 API
感知: 看到 ASCII 猫变成"真正的画"——极强的情感冲击
限制: 成本控制是关键 (按需 + 缓存 + 上限)
最佳时机: hatch 出生照 (第一张图) 的转化价值最高
```

### 视频 — 🟡 低优先级

```
投入: 高 (AI 视频 API 贵/慢)
替代: 幻灯片 + ASCII 帧动画 = 80% 效果, 5% 成本
建议: 用前端 Canvas 做帧动画 GIF, 不调 AI 生视频
```

### 综合判断

| 层级 | 内容 | 价值 | 成本 | 实施 |
|------|------|:--:|:--:|------|
| L1 | 形象演化 (kitten/adult/soulmate 帧) | ⭐⭐⭐⭐⭐ | 极低 | 立即 |
| L2 | prompt 拼装函数 | ⭐⭐⭐⭐ | 极低 | 立即 |
| L3 | hatch 出生照 (1 张生图) | ⭐⭐⭐⭐⭐ | 低 | P1 |
| L4 | 成长相册 (milestone 图) | ⭐⭐⭐⭐ | 中 | P2 |
| L5 | 幻灯片视频 (模板) | ⭐⭐⭐ | 低 | P3 |
| L6 | AI 生视频 | ⭐⭐ | 高 | P4 |
