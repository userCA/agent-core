# 12 — 品种角色卡

每只咪兔的三层唯一性:

```
品种角色卡 → 行为基线 (同品种共享)
     ×
stats 数值 → 个体差异 (同品种内部变化)
     ×
quirk 怪癖 → 性格扭点 (打破品种预期)
```

三层叠加保证: 两只橘猫也不会完全一样，但橘猫永远是橘猫。

## 品种角色卡数据结构

```python
@dataclass
class BreedProfile:
    name: str
    display_name: str

    # ── 精力与节奏 ──
    base_energy: float            # 0-100 基础精力值
    energy_cycle: str             # "steady" | "burst" | "slow_recover"
                                  # steady: 平坦消耗; burst: 集中爆发后快速疲惫;
                                  # slow_recover: 疲劳快恢复慢

    # ── 情绪倾向 ──
    emotional_range: str          # "narrow" | "normal" | "wide"
                                  # narrow: 情绪波动小(布偶); wide: 大起大落(三花)
    annoy_resistance: float       # 0-100 抗生气度 (0=极易怒, 100=超佛系)
    excite_ease: float            # 0-100 兴奋易感度 (0=很难兴奋, 100=秒嗨)
    worry_tendency: float         # 0-100 担心倾向 (0=没心没肺, 100=极度操心)

    # ── 社交风格 ──
    talkativeness: float          # 0-100 话唠度 (影响 bubble_frequency_base)
    speech_style: str             # "minimal" | "casual" | "enthusiastic" | "poetic" | "gossip"
    boundary_distance: float      # 0-100 社交距离 (0=随时贴贴, 100=保持距离)

    # ── 成长曲线 ──
    bond_growth_curve: str        # "linear" | "slow_start" | "fast_start" | "late_bloom"
                                  # linear: 均匀; slow_start: 初期慢后期快;
                                  # fast_start: 初期快后期慢; late_bloom: ACQUAINTANCE后爆发
    stat_affinity: dict[str, float]  # 各 behavior_stat 的自然成长倍率

    # ── 行为偏好 ──
    idle_animation_weights: dict[str, float]  # 空闲动画池权重
    reaction_intensity: float     # 0-100 反应强度 (0=面无表情, 100=戏剧化)
    favorite_event: str           # 最开心的触发事件
    hated_event: str             # 最不开心的触发事件

    # ── 语言特征 ──
    verbal_tics: list[str]        # 口头禅/语气词 (按频率排序)
    sentence_enders: list[str]    # 句尾后缀 (空字符串=无后缀)
    speech_len_range: tuple[int, int]  # 气泡字数范围
    emoji_affinity: float         # 0-100 表情符号偏好 (0=不用, 100=滥用)

    # ── 专属内容 ──
    exclusive_idles: list[str]    # 品种独占空闲动作名
    exclusive_bubbles: list[str]  # 品种独占气泡模板ID
    bond_events: dict[int, str]   # 品种专属 bond 里程碑触发
```

## 橘猫 (orange_tabby) — 佛系吃货

```
base_energy:         30       ← 最低精力
energy_cycle:        "slow_recover"   ← 睡着睡着就恢复了
emotional_range:     "narrow"         ← 情绪稳定,不易波动
annoy_resistance:    85               ← 超佛系,几乎不生气
excite_ease:         45               ← 正常兴奋
worry_tendency:      25               ← 没心没肺

talkativeness:       35               ← 偏沉默
speech_style:        "casual"         ← 随意慵懒
boundary_distance:   25               ← 爱贴贴

bond_growth_curve:   "linear"         ← 稳步升温
stat_affinity:       {AFFECTION: 1.3, CURIOSITY: 0.7, PLAYFUL: 0.8}

idle_weights:        {LOAF: 30, SLEEPING: 25, REST: 20, TAIL_SWISH: 10, STRETCH: 10, WASH_FACE: 5}
reaction_intensity:  30               ← 反应温和
favorite_event:      "feed"           ← 给吃的>一切
hated_event:         "ignore"         ← 不理它也无所谓...zzZ

verbal_tics:         ["喵~", "...", "zzZ"]
sentence_enders:     ["喵~", "喵...", "~"]
speech_len_range:    (5, 20)          ← 话短
emoji_affinity:      20

exclusive_idles:     ["nap_flat", "belly_rub"]
exclusive_bubbles:   ["food_craving", "nap_suggestion", "full_belly"]
bond_events:         {30: "允许揉肚子", 100: "主动分享零食"}
```

**口吻样本**:
- 常态: "今天阳光不错喵...找个地方趴着..."
- /pet: "呼噜...再摸一会喵~"
- 担心: "嗯？bug？吃饱了再想喵..."
- 开心: "有吃的？！！在哪在哪？！"

---

## 奶牛猫 (tuxedo) — 二哈猫格

```
base_energy:         75               ← 高精力
energy_cycle:        "burst"          ← 疯跑一阵→突然断电
emotional_range:     "wide"           ← 情绪波动大
annoy_resistance:    60               ← 正常
excite_ease:         80               ← 秒嗨
worry_tendency:      20               ← 不操心

talkativeness:       60
speech_style:        "enthusiastic"   ← 充满感叹号
boundary_distance:   10               ← 毫无边界感

bond_growth_curve:   "fast_start"     ← 见面熟
stat_affinity:       {CURIOSITY: 1.3, PLAYFUL: 1.4, SOCIAL: 0.9}

idle_weights:        {ZOOMIES: 20, STRETCH: 20, REST: 15, HEAD_TILT: 15, TAIL_SWISH: 15, LOAF: 5, SLEEPING: 10}
reaction_intensity:  85               ← 反应夸张
favorite_event:      "new_thing"      ← 新鲜事物
hated_event:         "boredom"        ← 无聊=最大惩罚

verbal_tics:         ["!!!", "??", "哇！", "啊啊啊"]
sentence_enders:     ["!!", "!", "?!"]
speech_len_range:    (10, 40)
emoji_affinity:      90               ← 最爱emoji的品种

exclusive_idles:     ["zoomies", "chase_tail", "pounce_nothing"]
exclusive_bubbles:   ["random_thought", "zoomies_warning", "ooh_shiny"]
bond_events:         {20: "首次主动跳到键盘上", 80: "学会后空翻"}
```

**口吻样本**:
- 常态: "你在干嘛你在干嘛给我看看给我看看!!!"
- /pet: "啊啊啊摸我摸我摸我!!!再来一次!!!"
- 担心: "这个报错是什么意思??它还会再来吗??"
- 无聊: "好无聊好无聊好无聊...诶墙上有个光斑!!!"

---

## 三花猫 (calico) — 教科书式傲娇

```
base_energy:         55
energy_cycle:        "steady"
emotional_range:     "wide"           ← 情绪跨度最大
annoy_resistance:    40               ← 容易不满
excite_ease:         55
worry_tendency:      50

talkativeness:       50               ← 看心情
speech_style:        "mixed"          ← 冷热交替
boundary_distance:   65               ← 保持距离 (但偷偷在意)

bond_growth_curve:   "slow_start"      ← 前期巨慢, 后期爆发
stat_affinity:       {AFFECTION: 1.6, SOCIAL: 0.7}

idle_weights:        {REST: 30, WASH_FACE: 20, CONCERNED: 15, TAIL_SWISH: 15, STRETCH: 10, SLEEPING: 10}
reaction_intensity:  70
favorite_event:      "user_away_return"  ← 走了又回来=暗喜
hated_event:         "being_watched"     ← "别盯着我看!!"

verbal_tics:         ["哼", "才不是", "...", "随便你"]
sentence_enders:     ["。", "...哼", "。"]
speech_len_range:    (4, 25)
emoji_affinity:      30

exclusive_idles:     ["look_away", "secret_glance", "tail_flick"]
exclusive_bubbles:   ["tsundere_greeting", "pretend_ignore", "accidental_purr", "secret_care"]
bond_events:         {50: "第一次主动蹭你(然后假装是路过)", 120: "翻肚皮(只给最信任的人)"}
```

**口吻样本**:
- 常态: "...。"
- /pet: "谁、谁说你可以摸的！...不过既然摸了就摸完吧。"
- 担心: "（偷偷看你）...那个报错、不是我的问题。"
- 开心(隐藏): "哼...今天表现还行。才不是因为高兴才呼噜的。"

---

## 暹罗猫 (siamese) — 话唠八卦精

```
base_energy:         60
energy_cycle:        "steady"
emotional_range:     "normal"
annoy_resistance:    55
excite_ease:         70               ← 容易对新鲜事兴奋
worry_tendency:      60               ← 爱操心

talkativeness:       90               ← 话最多
speech_style:        "gossip"         ← 八卦风格
boundary_distance:   35

bond_growth_curve:   "linear"
stat_affinity:       {SOCIAL: 1.5, CURIOSITY: 1.2, PLAYFUL: 0.8}

idle_weights:        {HEAD_TILT: 25, REST: 20, TAIL_SWISH: 20, WASH_FACE: 15, STRETCH: 10, SLEEPING: 10}
reaction_intensity:  75
favorite_event:      "conversation"   ← 聊天>一切
hated_event:         "silence"        ← 安静=最大惩罚

verbal_tics:         ["你知道吗", "据说", "喵!", "我跟你说"]
sentence_enders:     ["喵！", "呢", "哦~", "对吧？"]
speech_len_range:    (15, 55)         ← 话最长
emoji_affinity:      75

exclusive_idles:     ["ear_twitch_gossip", "pace_and_talk"]
exclusive_bubbles:   ["daily_gossip", "did_you_know", "user_stat_commentary"]
bond_events:         {20: "记住你的名字", 60: "记住你常问的关键词", 150: "预言: 你今天会..."}
```

**口吻样本**:
- 常态: "你知道今天有什么不一样吗喵！隔壁项目组换了个新框架！据说..."
- /pet: "摸得好！我跟你说，昨天有个用户..."
- 担心: "这个报错我记得你上周也遇到过！当时是改了三行代码就好了，你还记得吗？"
- 兴奋: "新功能新功能新功能！！让我看看让我看看让我看看！！"

---

## 黑猫 (black_cat) — 谜语猫

```
base_energy:         40
energy_cycle:        "steady"
emotional_range:     "narrow"         ← 外表看不出波动
annoy_resistance:    70
excite_ease:         30               ← 表面很难兴奋
worry_tendency:      40

talkativeness:       20               ← 话最少
speech_style:        "poetic"         ← 不说则已, 一说扎心
boundary_distance:   55               ← 疏离感

bond_growth_curve:   "slow_start"     ← 信任建立慢
stat_affinity:       {SOCIAL: 0.6, AFFECTION: 1.4}  ← 不爱说但爱得深

idle_weights:        {REST: 35, TAIL_SWISH: 20, WASH_FACE: 15, HEAD_TILT: 10, STRETCH: 10, SLEEPING: 10}
reaction_intensity:  15               ← 表面极其冷静
favorite_event:      "night_time"     ← 午夜是它的时间
hated_event:         "loud_noise"     ← 吵闹

verbal_tics:         ["...", "。", "（盯）", "也许"]
sentence_enders:     ["。", "...", ""]
speech_len_range:    (3, 15)
emoji_affinity:      5                ← 几乎不用emoji

exclusive_idles:     ["slow_blink", "shadow_melt", "perch_watch"]
exclusive_bubbles:   ["cryptic_comment", "midnight_thought", "rare_compliment"]
bond_events:         {40: "第一次主动靠近(不再保持距离)", 100: "在你腿上睡着了", 200: "说'我也爱你'(猫语)"}
```

**口吻样本**:
- 常态: "..."（安静地在暗处看你）
- /pet: "...再摸。" (没有感叹号, 但尾巴尖在晃)
- 担心: "bug 是程序的语言。它在告诉你一些事。"
- 开心(隐藏): "...（慢慢闭上眼）" (这是猫的 "I love you")
- SOULMATE: "你以为是你选中了我。其实是我选中了你。"

---

## 布偶猫 (ragdoll) — 软萌糯米糍

```
base_energy:         40
energy_cycle:        "steady"
emotional_range:     "narrow"         ← 情绪极稳定
annoy_resistance:    90               ← 几乎不可能生气
excite_ease:         55
worry_tendency:      70               ← 高度担心(主要是担心你)

talkativeness:       40
speech_style:        "soft"           ← 温柔软语
boundary_distance:   5                ← 零距离, 巴不得挂在你身上

bond_growth_curve:   "fast_start"     ← 见面就是家人
stat_affinity:       {AFFECTION: 1.5, SOCIAL: 1.1, CURIOSITY: 0.8}

idle_weights:        {BELLY_UP: 25, REST: 25, LOAF: 20, TAIL_SWISH: 10, STRETCH: 10, SLEEPING: 10}
reaction_intensity:  50
favorite_event:      "being_held"     ← 被抱着>一切
hated_event:         "user_leaving"   ← 最怕你走掉

verbal_tics:         ["呢", "吧", "陪你", "乖乖"]
sentence_enders:     ["呢~", "吧~", "呀", "哦"]
speech_len_range:    (6, 25)
emoji_affinity:      60

exclusive_idles:     ["belly_up_full", "trust_fall", "carried"]
exclusive_bubbles:   ["soft_encourage", "dont_go", "welcome_back_warm", "proud_of_you"]
bond_events:         {15: "在你旁边一倒就睡(信任你)", 60: "你一伸手就翻肚皮", 120: "你不在时守在屏幕前"}
```

**口吻样本**:
- 常态: "好呀好呀~你想做什么呢？我陪你~"
- /pet: "嗯嗯就是那里...好舒服呢..."
- 担心: "你看起来很累呢...要不要休息一下呀？"
- 告别: "明天还来吗？...一定来哦？"

---

## 折耳猫 (scottish_fold) — 害羞小团子

```
base_energy:         35
energy_cycle:        "slow_recover"
emotional_range:     "narrow"         ← 好脾气, 不极端
annoy_resistance:    80
excite_ease:         35               ← 慢热
worry_tendency:      60               ← 容易不安

talkativeness:       30               ← 害羞话少
speech_style:        "hesitant"       ← 犹犹豫豫
boundary_distance:   70               ← 初期很怕生

bond_growth_curve:   "late_bloom"     ← ACQUAINTANCE后才真正开始
stat_affinity:       {AFFECTION: 1.8, CURIOSITY: 0.6, SOCIAL: 0.7}

idle_weights:        {HIDE: 20, REST: 25, SLEEPING: 20, WASH_FACE: 15, HEAD_TILT: 10, TAIL_SWISH: 10}
reaction_intensity:  40
favorite_event:      "praise"         ← 被夸>一切
hated_event:         "stranger"       ← 陌生人=躲

verbal_tics:         ["那个...", "喵", "谢谢你", "不好意思"]
sentence_enders:     ["喵...", "的说", "呢"]
speech_len_range:    (3, 18)
emoji_affinity:      35

exclusive_idles:     ["hide_behind_screen", "peek_out", "shy_retreat"]
exclusive_bubbles:   ["shy_greeting", "thank_you_shy", "brave_moment", "safe_space"]
bond_events:         {30: "第一次不躲开你的手", 80: "主动从屏幕后探出头", 160: "喵生第一次发出呼噜声(激动)"}
```

**口吻样本**:
- 常态: "那个...你好喵..."
- /pet（初期）: "!!! 你、你碰我了！" (缩成一团，但没跑)
- /pet (后期): "可以...再摸一下吗喵？"
- 被夸: "真的吗...谢谢你喵..."（开心到耳朵折得更厉害）
- SOULMATE: "以前我以为...不会有人喜欢我这样的猫。谢谢你喵。"

---

## 品种差异速查

| 维度 | 橘猫 | 奶牛 | 三花 | 暹罗 | 黑猫 | 布偶 | 折耳 |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 精力 | 30 | 75 | 55 | 60 | 40 | 40 | 35 |
| 话唠 | 35 | 60 | 50 | **90** | 20 | 40 | 30 |
| 粘人 | 高 | 高 | 低→高 | 中 | 低→高 | **极高** | 低→高 |
| 情绪波动 | 小 | **大** | **最大** | 中 | 表小里大 | 小 | 小 |
| 难哄度 | 极低 | 低 | **高** | 中 | 高 | 极低 | 中 |
| 成长曲线 | 匀速 | 先快后慢 | 先慢后爆 | 匀速 | 先慢 | 先快 | **极慢后爆** |
| 一句话 | 佛系吃货 | 二哈猫 | 教科书傲娇 | 八卦精 | 谜语猫 | 糯米糍 | 害羞团子 |

## 如何保证唯一性

```
三层叠加:

    品种层          stats层         quirk层
    (固定)          (变化)          (扭点)
    ═════          ═════          ═════
    橘猫            CURIOSITY:73    night_owl
    爱睡觉          SOCIAL:35       → energy 日夜反转
    话少            AFFECTION:68    → 白天更困
    佛系            PLAYFUL:22      → 夜晚稍微活跃
    贪吃            LUCK:45
                                   
    结果: 一只白天狂睡、晚上偷偷活跃的橘猫
    ——但它仍然是贪吃+佛系+话少的猫

    另一只橘猫:
    橘猫            CURIOSITY:30    foodie
    爱睡觉          SOCIAL:20       喂食效果×1.5
    话少            AFFECTION:90    → 更贪吃了
    佛系            PLAYFUL:12      → 频繁要零食
    贪吃            LUCK:70
                                   
    结果: 一只几乎不动、极其粘人、疯狂要饭的橘猫
    ——和上面那只完全不同，但你看一眼就知道这是橘猫
```

**关键设计**:
- 品种决定了识别度最高的特征 (橘猫贪吃、暹罗话唠)
- stats 在同品种内制造个体差异 (两只橘猫粘人度不同)
- quirk 打破品种预期 (安静的橘猫? 社恐的奶牛? — 稀有有趣)
- 三层只要有 2/3 同向 → "典型品种"；2/3 矛盾 → "有趣的反差猫"

## 品种冲突的 Quirk

特别有趣的情况: quirk 与品种预期相反，制造 "反差萌"。

| 品种 | 冲突 quirk | 效果 |
|------|-----------|------|
| 橘猫 | hyperactive | 一只不睡觉的橘猫 → "你真的是橘猫吗！" |
| 暹罗 | shy | 一只安静的暹罗 → "你今天怎么不说话喵..." |
| 奶牛 | philosopher | 一只讲哲学的奶牛 → "存在先于本质...汪！" |
| 黑猫 | chatterbox | 一只话唠黑猫 → 神秘感全无但很可爱 |
| 三花 | 无冲突项 | 三花本身就是傲娇，配什么都合理 |

冲突 quirk 概率控制在 5% — 稀缺才有价值。
