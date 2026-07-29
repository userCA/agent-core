<template>
  <view class="history-page" :class="'theme-' + themeStore.theme">
    <!-- 搜索栏 -->
    <view class="search-bar">
      <input
        class="search-input"
        v-model="searchQuery"
        placeholder="搜索会话..."
        confirm-type="search"
      />
      <text v-if="searchQuery" class="search-clear" @tap="searchQuery = ''">✕</text>
    </view>

    <!-- 加载中 -->
    <view v-if="sessionStore.sessionsLoading" class="loading-state">
      <view class="spinner" />
      <text class="loading-text">加载中...</text>
    </view>

    <!-- 空状态 -->
    <view v-else-if="!searchQuery && sessionStore.sessions.length === 0" class="empty-state">
      <text class="empty-icon">💬</text>
      <text class="empty-text">暂无历史记录</text>
    </view>

    <!-- 搜索无结果 -->
    <view v-else-if="searchQuery && filteredSessions.length === 0" class="empty-state">
      <text class="empty-icon">🔍</text>
      <text class="empty-text">未找到匹配的会话</text>
    </view>

    <!-- 会话列表 -->
    <scroll-view v-else class="session-list" scroll-y>
      <view v-for="(group, gi) in groupedSessions" :key="gi" class="date-group">
        <text class="date-label">{{ group.label }}</text>
        <view
          v-for="s in group.items"
          :key="s.session_id"
          class="session-item"
          :class="{ 'session-item--active': s.session_id === sessionStore.sessionId }"
        >
          <view class="session-main" @tap="handleSwitch(s.session_id)">
            <text class="session-title">{{ s.title || '新会话' }}</text>
            <text class="session-meta">{{ s.entry_count }} 条消息</text>
          </view>
          <view
            class="session-delete"
            :class="{ 'session-delete--loading': deletingId === s.session_id }"
            @tap.stop="handleDelete(s.session_id)"
          >
            <text v-if="deletingId === s.session_id" class="delete-spinner">⟳</text>
            <text v-else class="delete-icon">🗑</text>
          </view>
        </view>
      </view>
      <!-- 底部间距 -->
      <view style="height: 40rpx;" />
    </scroll-view>
  </view>
</template>

<script>
import { sessionStore } from '../../stores/session.js';
import { chatStore } from '../../stores/chat.js';
import { themeStore } from '../../stores/theme.js';

/**
 * 格式化日期分组标签
 */
function formatDateGroup(dateStr) {
  const date = new Date(dateStr);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  if (isToday) return '今天';

  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return '昨天';

  const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const dayName = days[date.getDay()];
  const month = date.getMonth() + 1;
  const day = date.getDate();
  return `${month}月${day}日 · ${dayName}`;
}

export default {
  data() {
    return {
      sessionStore,
      themeStore,
      searchQuery: '',
      deletingId: null,
    };
  },

  computed: {
    filteredSessions() {
      const q = this.searchQuery.trim().toLowerCase();
      if (!q) return sessionStore.sessions;
      return sessionStore.sessions.filter((s) =>
        (s.title || '').toLowerCase().includes(q),
      );
    },

    groupedSessions() {
      const groups = [];
      let currentLabel = '';
      let currentItems = [];

      for (const s of this.filteredSessions) {
        const label = formatDateGroup(s.created_at);
        if (label !== currentLabel) {
          if (currentItems.length > 0) {
            groups.push({ label: currentLabel, items: currentItems });
          }
          currentLabel = label;
          currentItems = [s];
        } else {
          currentItems.push(s);
        }
      }
      if (currentItems.length > 0) {
        groups.push({ label: currentLabel, items: currentItems });
      }
      return groups;
    },
  },

  onShow() {
    sessionStore.loadSessions();
  },

  methods: {
    async handleSwitch(sessionId) {
      sessionStore.switchSession(sessionId);
      chatStore.reset();
      await chatStore.loadMessages(sessionId);
      chatStore.setWelcomeVisible(false);
      uni.switchTab({ url: '/pages/chat/index' });
    },

    async handleDelete(sessionId) {
      if (this.deletingId) return;

      uni.showModal({
        title: '删除会话',
        content: '确定删除此会话？此操作不可恢复。',
        success: async (res) => {
          if (!res.confirm) return;
          this.deletingId = sessionId;
          try {
            await sessionStore.deleteSession(sessionId);
            uni.showToast({ title: '已删除', icon: 'success' });
          } catch (e) {
            uni.showToast({ title: '删除失败', icon: 'none' });
          } finally {
            this.deletingId = null;
          }
        },
      });
    },
  },
};
</script>

<style scoped>
.history-page {
  height: 100vh;
  background: #f5f5f5;
  display: flex;
  flex-direction: column;
}

/* ---- Search ---- */
.search-bar {
  display: flex;
  align-items: center;
  padding: 16rpx 24rpx;
  background: #fff;
  border-bottom: 1rpx solid #eee;
  gap: 12rpx;
}

.search-input {
  flex: 1;
  height: 64rpx;
  padding: 0 24rpx;
  background: #f5f5f5;
  border-radius: 32rpx;
  font-size: 28rpx;
}

.search-clear {
  font-size: 28rpx;
  color: #999;
  padding: 8rpx;
}

/* ---- Loading ---- */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 200rpx;
  gap: 16rpx;
}

.spinner {
  width: 48rpx;
  height: 48rpx;
  border: 4rpx solid #eee;
  border-top-color: #333;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  font-size: 26rpx;
  color: #999;
}

/* ---- Empty ---- */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 200rpx;
  gap: 16rpx;
}

.empty-icon {
  font-size: 64rpx;
}

.empty-text {
  font-size: 28rpx;
  color: #999;
}

/* ---- Session List ---- */
.session-list {
  flex: 1;
  padding: 16rpx 24rpx;
}

.date-group {
  margin-bottom: 24rpx;
}

.date-label {
  font-size: 24rpx;
  color: #999;
  font-weight: 600;
  padding: 8rpx 0;
  display: block;
}

.session-item {
  display: flex;
  align-items: center;
  background: #fff;
  border-radius: 16rpx;
  margin-bottom: 12rpx;
  overflow: hidden;
  border: 2rpx solid transparent;
}

.session-item--active {
  border-color: #1a1a2e;
}

.session-main {
  flex: 1;
  padding: 24rpx;
  display: flex;
  flex-direction: column;
  gap: 8rpx;
  min-width: 0;
}

.session-title {
  font-size: 28rpx;
  color: #333;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-meta {
  font-size: 22rpx;
  color: #999;
}

.session-delete {
  width: 80rpx;
  height: 80rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.session-delete--loading {
  opacity: 0.5;
}

.delete-icon {
  font-size: 28rpx;
}

.delete-spinner {
  font-size: 28rpx;
  animation: spin 0.8s linear infinite;
}
</style>
