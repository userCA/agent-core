<template>
  <view class="login-page" :class="'theme-' + themeStore.theme">
    <view class="login-container">
      <!-- Logo -->
      <view class="login-logo">
        <image class="login-logo-img" src="/static/logo.png" mode="aspectFit" />
      </view>

      <text class="login-brand">咪兔</text>
      <text class="login-tagline">你的 AI 伙伴</text>

      <!-- 输入表单 -->
      <view class="login-form">
        <input
          class="login-input"
          type="text"
          v-model="uid"
          placeholder="输入用户 ID（留空自动生成）"
          :disabled="loading"
          confirm-type="done"
          @confirm="handleLogin"
        />
        <button
          class="login-btn"
          :disabled="loading"
          @tap="handleLogin"
        >
          {{ loading ? '连接中...' : '开始对话' }}
        </button>
      </view>

      <!-- 最近使用 -->
      <view v-if="sessionStore.knownUids.length > 0" class="login-recent">
        <text class="login-recent-title">最近使用</text>
        <view class="login-recent-list">
          <button
            v-for="u in sessionStore.knownUids"
            :key="u"
            class="login-recent-item"
            :disabled="loading"
            @tap="handleLoginWithUid(u)"
          >
            {{ u }}
          </button>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { sessionStore } from '../../stores/session.js';
import { themeStore } from '../../stores/theme.js';

function generateId() {
  const t = Date.now().toString(36);
  const r = Math.random().toString(36).slice(2, 6);
  return `user-${t}-${r}`;
}

export default {
  data() {
    return {
      uid: '',
      loading: false,
      sessionStore,
      themeStore,
    };
  },

  methods: {
    handleLogin() {
      const finalUid = (this.uid || generateId()).trim();
      if (!finalUid) return;
      this.loading = true;
      try {
        sessionStore.saveAuth({ uid: finalUid });
        sessionStore.registerUid(finalUid);
        uni.switchTab({ url: '/pages/chat/index' });
      } finally {
        this.loading = false;
      }
    },

    handleLoginWithUid(loginUid) {
      this.uid = loginUid;
      this.handleLogin();
    },
  },
};
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, #f0f4ff 0%, #ffffff 100%);
}

.login-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 60rpx;
  width: 100%;
}

.login-logo {
  margin-bottom: 40rpx;
}

.login-logo-img {
  width: 160rpx;
  height: 160rpx;
}

.login-brand {
  font-size: 56rpx;
  font-weight: 700;
  color: #1a1a2e;
  margin-bottom: 16rpx;
}

.login-tagline {
  font-size: 28rpx;
  color: #666;
  margin-bottom: 80rpx;
}

.login-form {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 24rpx;
}

.login-input {
  width: 100%;
  height: 88rpx;
  padding: 0 32rpx;
  border: 2rpx solid #e0e0e0;
  border-radius: 16rpx;
  font-size: 28rpx;
  background: #fff;
  box-sizing: border-box;
}

.login-btn {
  width: 100%;
  height: 88rpx;
  line-height: 88rpx;
  background: #1a1a2e;
  color: #fff;
  font-size: 30rpx;
  font-weight: 600;
  border-radius: 16rpx;
  border: none;
}

.login-btn[disabled] {
  opacity: 0.6;
}

.login-recent {
  width: 100%;
  margin-top: 60rpx;
}

.login-recent-title {
  font-size: 24rpx;
  color: #999;
  margin-bottom: 20rpx;
  display: block;
  text-align: center;
}

.login-recent-list {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 16rpx;
}

.login-recent-item {
  padding: 12rpx 28rpx;
  background: #f0f0f5;
  border-radius: 24rpx;
  font-size: 24rpx;
  color: #555;
  border: none;
  line-height: 1.4;
}

.login-recent-item[disabled] {
  opacity: 0.5;
}
</style>
