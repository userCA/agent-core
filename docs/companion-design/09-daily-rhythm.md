# 09 — 日周期

## 时间段定义 (用户本地时间)

```
06:00 - 09:00   MORNING      晨间
09:00 - 12:00   FORENOON     上午
12:00 - 14:00   NOON         午间
14:00 - 18:00   AFTERNOON    下午
18:00 - 20:00   EVENING      傍晚 (zoomies time)
20:00 - 23:00   NIGHT        晚间
23:00 - 06:00   LATE_NIGHT   深夜
```

## 时间乘数表

| 时段 | energy | mood 上限 | 气泡频率 | 动画池 | zzz 触发 |
|------|:---:|:---:|:---:|------|:--:|
| MORNING | ×0.7 | 80 | ×0.5 | 含 YAWN 帧 | 容易 (15min) |
| FORENOON | ×1.0 | 100 | ×1.0 | 正常 + PLAYFUL | 正常 (30min) |
| NOON | ×0.6 | 70 | ×0.4 | 含 SLEEPY 帧 | 容易 (10min) |
| AFTERNOON | ×1.0 | 100 | ×1.0 | 正常 | 正常 (30min) |
| EVENING | **×1.3** | 100 | **×1.5** | 活跃 + ZOOMIES 帧 | 困难 (60min) |
| NIGHT | ×0.9 | 90 | ×0.8 | 温和 + 趴卧帧 | 较易 (20min) |
| LATE_NIGHT | ×0.4 | 60 | ×0.2 | 深度睡眠帧 | **强制 (5min)** |

## quirk 覆盖

```
night_owl quirk:
  energy 反转: MORNING→×0.4, FORENOON→×0.5, NOON→×0.4,
               EVENING→×1.0, NIGHT→×1.3, LATE_NIGHT→×1.0

sleepyhead quirk:
  所有时段 zzz 触发时间减半
  LATE_NIGHT 强制 2min (而非 5min)
```

## 特殊时间触发

| 时间 | 触发 | 反应 |
|------|------|------|
| 首次 03:00-05:00 登录 | late_night_first | "这个点你居然在！既然来了就陪你" |
| 12:00 整 | noon_chime | "午饭时间喵~" |
| 日落 (18:00-18:05) | sunset_zoomies | ZOOMIES 帧强制触发 |
| 00:00 跨日 | midnight | "新的一天！昨天不错喵" |
| 用户生日* | birthday | 庆生气泡 + 专属动画 |

*生日来自配置，可选。

## 实现

```python
class DailyRhythm:
    @staticmethod
    def get_period(hour: int) -> str:
        if 6 <= hour < 9:   return "MORNING"
        if 9 <= hour < 12:  return "FORENOON"
        if 12 <= hour < 14: return "NOON"
        if 14 <= hour < 18: return "AFTERNOON"
        if 18 <= hour < 20: return "EVENING"
        if 20 <= hour < 23: return "NIGHT"
        return "LATE_NIGHT"
    
    @staticmethod
    def energy_multiplier(period: str, quirk: str) -> float:
        base = PERIOD_TABLE[period].energy_mult
        if quirk == "night_owl":
            return 1.3 - base  # 反转
        if quirk == "sleepyhead":
            return base * 0.7
        return base
    
    @staticmethod
    def animation_pool(period: str, bond: int) -> list[str]:
        """返回当前时段可用的动画帧名列表."""
        base = PERIOD_TABLE[period].animations
        if bond >= BOND_FRIEND:
            base += ["SLOW_BLINK"]  # 老朋友了，白天也可以慢眨眼
        return base
```
