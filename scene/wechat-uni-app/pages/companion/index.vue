<template>
  <view class="companion-page" :class="'theme-' + themeStore.theme">
    <!-- 头像区 -->
    <view class="avatar-section">
      <view class="avatar-wrapper">
        <image class="avatar-img" src="/static/logo.png" mode="aspectFit" />
        <text v-if="bones.shiny" class="shiny-badge">✦</text>
        <!-- 心情角标 -->
        <view class="mood-badge">
          <text class="mood-emoji">{{ moodEmoji }}</text>
        </view>
      </view>
      <text class="companion-name">{{ bones.name || '未命名' }}</text>
      <text
        class="rarity-tag"
        :style="{ color: rarityColor, borderColor: rarityColor }"
      >{{ rarityLabel }}</text>
      <text class="personality">{{ bones.personality || '一只神秘的咪兔' }}</text>
      <view class="meta-row">
        <text class="meta-item">{{ breedLabel }}</text>
        <text v-if="bones.hatched_at" class="meta-item">{{ formatDate(bones.hatched_at) }}</text>
      </view>
    </view>

    <!-- 当前心情 -->
    <view class="card mood-card">
      <text class="card-title">🌙 心情</text>
      <view class="mood-display">
        <text class="mood-face">{{ moodEmoji }}</text>
        <view class="mood-info">
          <text class="mood-label">{{ moodLabel }}</text>
          <text v-if="companionStore.bubble" class="mood-bubble">“{{ companionStore.bubble.text }}”</text>
          <text v-else class="mood-desc">{{ moodDesc }}</text>
        </view>
      </view>
    </view>

    <!-- 亲密度 -->
    <view class="card">
      <text class="card-title">❤️ 亲密度</text>
      <view class="bond-info">
        <view class="bond-header">
          <text class="bond-label">{{ bondLevel.display }}</text>
          <text class="bond-score">{{ bondScore }} 分</text>
        </view>
        <view class="bond-bar">
          <view class="bond-fill" :style="{ width: bondProgress + '%' }" />
        </view>
        <text class="bond-desc">{{ bondLevel.desc }}</text>
      </view>
    </view>

    <!-- 属性 -->
    <view v-if="statEntries.length > 0" class="card">
      <text class="card-title">📊 属性</text>
      <view class="stats-grid">
        <view v-for="item in statEntries" :key="item.key" class="stat-item">
          <view class="stat-header">
            <text class="stat-name">{{ item.key }}</text>
            <text class="stat-value">{{ item.value }}</text>
          </view>
          <view class="stat-bar">
            <view class="stat-fill" :style="{ width: item.value + '%' }" />
          </view>
        </view>
      </view>
    </view>

    <!-- 怪癖 -->
    <view v-if="quirkLabel" class="card">
      <text class="card-title">✨ 怪癖</text>
      <text class="quirk-tag">{{ quirkLabel }}</text>
    </view>

    <!-- 外观 -->
    <view class="card">
      <text class="card-title">👁 外观</text>
      <view class="appearance-grid">
        <view class="appearance-item">
          <text class="appearance-label">眼睛</text>
          <text class="appearance-value">{{ bones.eye || '默认' }}</text>
        </view>
        <view class="appearance-item">
          <text class="appearance-label">耳朵</text>
          <text class="appearance-value">{{ bones.ear || '默认' }}</text>
        </view>
        <view class="appearance-item">
          <text class="appearance-label">配饰</text>
          <text class="appearance-value">{{ bones.hat && bones.hat !== 'none' ? bones.hat : '无' }}</text>
        </view>
        <view class="appearance-item">
          <text class="appearance-label">闪亮</text>
          <text class="appearance-value">{{ bones.shiny ? '是' : '否' }}</text>
        </view>
      </view>
    </view>

    <!-- 互动按钮 -->
    <view class="actions">
      <button class="action-btn" @tap="handlePetReaction('poke')">戳一下</button>
      <button class="action-btn" @tap="handlePetReaction('feed')">喂零食</button>
      <button class="action-btn" @tap="handlePetReaction('praise')">表扬</button>
    </view>

    <view style="height: 40rpx;" />
  </view>
</template>

<script>
import { companionStore } from '../../stores/companion.js';
import { sessionStore } from '../../stores/session.js';
import { themeStore } from '../../stores/theme.js';

const RARITY_LABELS = {
  common: '普通', uncommon: '稀有', rare: '珍稀', epic: '史诗', legendary: '传说',
};

const RARITY_COLORS = {
  common: '#8e8e93', uncommon: '#30d158', rare: '#409cff', epic: '#bf5af2', legendary: '#ff9f0a',
};

const QUIRK_LABELS = {
  night_owl: '夜猫子', picky_eater: '挑食怪', chatterbox: '话痨',
  shy: '社恐', collector: '收集癖', hyperactive: '多动症',
  sleepyhead: '睡神', glass_heart: '玻璃心', foodie: '贪吃',
  clean_freak: '洁癖', tsundere_extreme: '究极傲娇', philosopher: '哲学家', comedian: '搞笑猫',
};

const BOND_LEVELS = [
  { threshold: 0, display: '陌生人', desc: '你们刚刚相遇' },
  { threshold: 10, display: '相识', desc: '开始记住你的名字' },
  { threshold: 50, display: '朋友', desc: '经常一起玩耍' },
  { threshold: 200, display: '知己', desc: '彼此非常了解' },
  { threshold: 1000, display: '灵魂伴侣', desc: '命中注定的羁绊' },
];

function getBondLevel(score) {
  for (let i = BOND_LEVELS.length - 1; i >= 0; i--) {
    if (score >= BOND_LEVELS[i].threshold) return BOND_LEVELS[i];
  }
  return BOND_LEVELS[0];
}

function getBondProgress(score) {
  const current = getBondLevel(score);
  const idx = BOND_LEVELS.indexOf(current);
  if (idx === BOND_LEVELS.length - 1) return 100;
  const next = BOND_LEVELS[idx + 1];
  const range = next.threshold - current.threshold;
  const progress = score - current.threshold;
  return Math.min(100, Math.max(0, (progress / range) * 100));
}

const MOOD_MAP = {
  sleeping: { emoji: '😴', label: '睡着了', desc: '正在美梦中...' },
  happy: { emoji: '😸', label: '开心', desc: '心情非常好！' },
  calm: { emoji: '😌', label: '平静', desc: '安静地待着' },
  sad: { emoji: '😿', label: '伤心', desc: '有点不开心...' },
  excited: { emoji: '🤩', label: '兴奋', desc: '超级期待！' },
  curious: { emoji: '🧐', label: '好奇', desc: '想探索新事物' },
  working: { emoji: '💪', label: '工作中', desc: '正在努力干活' },
  concerned: { emoji: '😟', label: '担忧', desc: '有什么烦心事' },
  awake: { emoji: '👀', label: '清醒', desc: '精神抖擞' },
};

export default {
  data() {
    return {
      companionStore,
      themeStore,
    };
  },

  computed: {
    bones() {
      return companionStore.bones || {};
    },

    rarityLabel() {
      return RARITY_LABELS[this.bones.rarity] || '普通';
    },

    rarityColor() {
      return RARITY_COLORS[this.bones.rarity] || '#8e8e93';
    },

    breedLabel() {
      return this.bones.breed || '未知品种';
    },

    quirkLabel() {
      return QUIRK_LABELS[this.bones.quirk] || this.bones.quirk || '';
    },

    bondScore() {
      return ((this.bones.stats || {}).AFFECTION || 50) * 5;
    },

    bondLevel() {
      return getBondLevel(this.bondScore);
    },

    bondProgress() {
      return getBondProgress(this.bondScore);
    },

    statEntries() {
      const stats = this.bones.stats || {};
      return Object.entries(stats).map(([key, value]) => ({ key, value }));
    },

    moodEmoji() {
      const mood = companionStore.mood || 'sleeping';
      return (MOOD_MAP[mood] || MOOD_MAP.calm).emoji;
    },

    moodLabel() {
      const mood = companionStore.mood || 'sleeping';
      return (MOOD_MAP[mood] || MOOD_MAP.calm).label;
    },

    moodDesc() {
      const mood = companionStore.mood || 'sleeping';
      return (MOOD_MAP[mood] || MOOD_MAP.calm).desc;
    },
  },

  onShow() {
    const uid = sessionStore.authHeaders?.uid;
    if (uid && !companionStore.revealed) {
      companionStore.reveal(uid);
    }
  },

  methods: {
    formatDate(ts) {
      const d = new Date(ts);
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    },

    handlePetReaction(type) {
      const name = this.bones.name || '咪兔';
      const reactions = {
        poke: `${name}咯咯笑着蹦来蹦去！`,
        feed: `${name}吃得很开心，真香！`,
        praise: `${name}骄傲地笑了！`,
      };
      uni.showToast({ title: reactions[type], icon: 'none', duration: 2000 });
    },
  },
};
</script>

<style scoped>
.companion-page {
  min-height: 100vh;
  background: #f5f5f5;
  padding: 24rpx;
}

/* ---- Avatar ---- */
.avatar-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40rpx 0 24rpx;
}

.avatar-wrapper {
  position: relative;
  width: 160rpx;
  height: 160rpx;
  margin-bottom: 20rpx;
}

.avatar-img {
  width: 160rpx;
  height: 160rpx;
  border-radius: 50%;
  background: #e8e8f0;
}

.shiny-badge {
  position: absolute;
  top: -8rpx;
  right: -8rpx;
  font-size: 36rpx;
  color: #ff9f0a;
}

/* ---- Mood Display ---- */
.mood-badge {
  position: absolute;
  bottom: -4rpx;
  right: -4rpx;
  width: 48rpx;
  height: 48rpx;
  border-radius: 50%;
  background: #fff;
  border: 2rpx solid #eee;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mood-emoji {
  font-size: 28rpx;
}

.mood-card {
  margin-top: 0;
}

.mood-display {
  display: flex;
  align-items: center;
  gap: 20rpx;
}

.mood-face {
  font-size: 64rpx;
  flex-shrink: 0;
}

.mood-info {
  flex: 1;
}

.mood-label {
  font-size: 30rpx;
  font-weight: 600;
  color: #1a1a2e;
  display: block;
  margin-bottom: 4rpx;
}

.mood-bubble,
.mood-desc {
  font-size: 24rpx;
  color: #888;
  display: block;
  line-height: 1.5;
}

.mood-bubble {
  font-style: italic;
}

.companion-name {
  font-size: 40rpx;
  font-weight: 700;
  color: #1a1a2e;
  margin-bottom: 8rpx;
}

.rarity-tag {
  font-size: 22rpx;
  padding: 4rpx 16rpx;
  border: 2rpx solid;
  border-radius: 16rpx;
  margin-bottom: 12rpx;
}

.personality {
  font-size: 26rpx;
  color: #888;
  margin-bottom: 12rpx;
}

.meta-row {
  display: flex;
  gap: 24rpx;
}

.meta-item {
  font-size: 22rpx;
  color: #999;
}

/* ---- Card ---- */
.card {
  background: #fff;
  border-radius: 16rpx;
  padding: 24rpx;
  margin-bottom: 16rpx;
}

.card-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #333;
  margin-bottom: 16rpx;
  display: block;
}

/* ---- Bond ---- */
.bond-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12rpx;
}

.bond-label {
  font-size: 28rpx;
  font-weight: 600;
  color: #1a1a2e;
}

.bond-score {
  font-size: 24rpx;
  color: #888;
}

.bond-bar {
  height: 12rpx;
  background: #f0f0f0;
  border-radius: 6rpx;
  overflow: hidden;
  margin-bottom: 12rpx;
}

.bond-fill {
  height: 100%;
  background: #ff6b6b;
  border-radius: 6rpx;
  transition: width 0.8s ease-out;
}

.bond-desc {
  font-size: 24rpx;
  color: #888;
}

/* ---- Stats ---- */
.stats-grid {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
}

.stat-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6rpx;
}

.stat-name {
  font-size: 24rpx;
  color: #555;
  font-weight: 500;
}

.stat-value {
  font-size: 24rpx;
  color: #888;
}

.stat-bar {
  height: 10rpx;
  background: #f0f0f0;
  border-radius: 5rpx;
  overflow: hidden;
}

.stat-fill {
  height: 100%;
  background: #409cff;
  border-radius: 5rpx;
  transition: width 0.8s ease-out;
}

/* ---- Quirk ---- */
.quirk-tag {
  display: inline-block;
  padding: 8rpx 24rpx;
  background: #f0f0ff;
  color: #6666cc;
  border-radius: 16rpx;
  font-size: 26rpx;
}

/* ---- Appearance ---- */
.appearance-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
}

.appearance-item {
  width: 48%;
  display: flex;
  justify-content: space-between;
}

.appearance-label {
  font-size: 24rpx;
  color: #888;
}

.appearance-value {
  font-size: 24rpx;
  color: #333;
  font-weight: 500;
}

/* ---- Actions ---- */
.actions {
  display: flex;
  gap: 16rpx;
  margin-top: 24rpx;
}

.action-btn {
  flex: 1;
  height: 72rpx;
  background: #fff;
  border: 2rpx solid #e0e0e0;
  border-radius: 36rpx;
  font-size: 26rpx;
  color: #555;
  line-height: 72rpx;
}

.action-btn::after {
  border: none;
}
</style>
