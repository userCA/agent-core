<template>
  <view class="settings-page" :class="'theme-' + themeStore.theme">
    <!-- 用户资料卡片 -->
    <view class="profile-card">
      <view class="profile-avatar">
        <text class="avatar-text">🐱</text>
      </view>
      <text class="profile-name">{{ currentPersonaName }}</text>
      <text v-if="currentSessionTitle" class="profile-session">{{ currentSessionTitle }}</text>
    </view>

    <!-- 通用设置 -->
    <view class="settings-card">
      <text class="card-title">通用</text>
      <view class="settings-body">
        <!-- 认证设置 -->
        <view class="setting-row" @tap="showAuthPanel = true">
          <view class="row-left">
            <text class="row-icon">🔑</text>
            <text class="row-label">认证设置</text>
          </view>
          <text class="row-arrow">›</text>
        </view>
        <!-- 主题切换 -->
        <view class="setting-row">
          <view class="row-left">
            <text class="row-icon">🎨</text>
            <text class="row-label">主题</text>
          </view>
          <view class="row-right">
            <text class="row-value">{{ themeStore.theme === 'dark' ? '暗色' : '亮色' }}</text>
            <switch
              :checked="themeStore.isDark"
              @change="themeStore.toggleTheme()"
              color="#1a1a2e"
            />
          </view>
        </view>
        <!-- 技能管理 -->
        <view class="setting-row" @tap="goToSkills">
          <view class="row-left">
            <text class="row-icon">⚡</text>
            <text class="row-label">技能管理</text>
          </view>
          <text class="row-arrow">›</text>
        </view>
      </view>
    </view>

    <!-- 专家角色 -->
    <view v-if="sessionStore.personas.length > 0" class="settings-card">
      <text class="card-title">专家</text>
      <view class="settings-body">
        <view
          v-for="p in sessionStore.personas"
          :key="p.id"
          class="setting-row"
          :class="{ 'row-active': sessionStore.personaId === p.id }"
          @tap="handleSelectPersona(p)"
        >
          <view class="row-left">
            <view class="persona-icon" :class="{ 'persona-active': sessionStore.personaId === p.id }">
              <text class="persona-icon-text">👤</text>
            </view>
            <text class="row-label">{{ p.name }}</text>
          </view>
          <text v-if="sessionStore.personaId === p.id" class="check-icon">✓</text>
        </view>
      </view>
    </view>

    <!-- 模型选择 -->
    <view v-if="models.length > 1" class="settings-card">
      <text class="card-title">模型</text>
      <view class="settings-body">
        <picker
          :range="modelLabels"
          :value="currentModelIndex"
          @change="handleModelChange"
        >
          <view class="setting-row">
            <view class="row-left">
              <text class="row-icon">🤖</text>
              <text class="row-label">当前模型</text>
            </view>
            <view class="row-right">
              <text class="row-value">{{ currentModelLabel }}</text>
              <text class="row-arrow">›</text>
            </view>
          </view>
        </picker>
      </view>
    </view>

    <!-- 账户 -->
    <view class="settings-card">
      <text class="card-title">账户</text>
      <view class="settings-body">
        <view class="setting-row setting-row-danger" @tap="handleLogout">
          <view class="row-left">
            <text class="row-icon">🚪</text>
            <text class="row-label">退出登录</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 底部品牌 -->
    <text class="footer-brand">咪兔</text>

    <!-- 认证面板弹窗 -->
    <view v-if="showAuthPanel" class="modal-backdrop" @tap="showAuthPanel = false">
      <view class="auth-panel" @tap.stop>
        <view class="auth-header">
          <text class="auth-title">认证设置</text>
          <button
            class="btn-save"
            :disabled="saving"
            @tap="handleSaveAuth"
          >
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </view>
        <view class="auth-body">
          <view v-for="key in authKeys" :key="key" class="auth-field">
            <text class="auth-label">{{ key }}</text>
            <input
              class="auth-input"
              :type="key === 'pacmtoken' ? 'password' : 'text'"
              :value="authValues[key] || ''"
              @input="authValues[key] = $event.detail.value"
              :placeholder="key"
            />
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { sessionStore } from '../../stores/session.js';
import { themeStore } from '../../stores/theme.js';
import { fetchModels } from '../../api/client.js';
import { AUTH_KEYS } from '../../api/config.js';

export default {
  data() {
    return {
      sessionStore,
      themeStore,
      authKeys: AUTH_KEYS,
      showAuthPanel: false,
      saving: false,
      authValues: {},
      models: [],
      currentProvider: '',
      currentModel: '',
    };
  },

  computed: {
    currentPersonaName() {
      const p = sessionStore.personas.find((p) => p.id === sessionStore.personaId);
      return p ? p.name : '访客';
    },
    currentSessionTitle() {
      const s = sessionStore.sessions.find((s) => s.session_id === sessionStore.sessionId);
      return s ? s.title : '';
    },
    modelLabels() {
      return this.models.map((m) => m.label || `${m.provider}/${m.model}`);
    },
    currentModelLabel() {
      const m = this.models.find(
        (m) => m.provider === this.currentProvider && m.model === this.currentModel
      );
      return m ? (m.label || `${m.provider}/${m.model}`) : '默认';
    },
    currentModelIndex() {
      return this.models.findIndex(
        (m) => m.provider === this.currentProvider && m.model === this.currentModel
      );
    },
  },

  onLoad() {
    sessionStore.loadPersonas();
    // 初始化 authValues
    for (const k of AUTH_KEYS) {
      this.authValues[k] = sessionStore.authHeaders[k] || '';
    }
    // 加载模型列表
    this.loadModels();
  },

  onShow() {
    // 每次显示时刷新 authValues
    for (const k of AUTH_KEYS) {
      this.authValues[k] = sessionStore.authHeaders[k] || '';
    }
  },

  methods: {
    async loadModels() {
      try {
        const data = await fetchModels();
        this.models = data.available || [];
        this.currentProvider = data.current?.provider || '';
        this.currentModel = data.current?.model || '';
      } catch (e) {
        // 静默降级
      }
    },
    handleModelChange(e) {
      const idx = e.detail.value;
      const m = this.models[idx];
      if (m) {
        this.currentProvider = m.provider;
        this.currentModel = m.model;
      }
    },
    handleSelectPersona(p) {
      sessionStore.setPersonaId(p.id);
      uni.showToast({ title: `已切换到「${p.name}」`, icon: 'success' });
    },
    goToSkills() {
      uni.navigateTo({ url: '/pages/skills/index' });
    },
    handleLogout() {
      uni.showModal({
        title: '确认退出',
        content: '退出后将清除本地登录信息',
        success: (res) => {
          if (res.confirm) {
            sessionStore.clearAuth();
            uni.showToast({ title: '已退出登录', icon: 'none' });
            uni.redirectTo({ url: '/pages/login/index' });
          }
        },
      });
    },
    async handleSaveAuth() {
      this.saving = true;
      try {
        sessionStore.saveAuth(this.authValues);
        this.showAuthPanel = false;
        uni.showToast({ title: '已保存', icon: 'success' });
      } catch (e) {
        uni.showToast({ title: '保存失败', icon: 'none' });
      } finally {
        this.saving = false;
      }
    },
  },
};
</script>

<style scoped>
.settings-page {
  min-height: 100vh;
  background: #f5f5f5;
  padding: 24rpx;
  padding-bottom: 60rpx;
}

/* Profile Card */
.profile-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48rpx 24rpx;
  background: #fff;
  border-radius: 24rpx;
  margin-bottom: 24rpx;
}

.profile-avatar {
  width: 120rpx;
  height: 120rpx;
  border-radius: 50%;
  background: #e8e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20rpx;
}

.avatar-text {
  font-size: 56rpx;
}

.profile-name {
  font-size: 36rpx;
  font-weight: 700;
  color: #1a1a2e;
  margin-bottom: 8rpx;
}

.profile-session {
  font-size: 24rpx;
  color: #888;
}

/* Settings Card */
.settings-card {
  background: #fff;
  border-radius: 20rpx;
  padding: 24rpx;
  margin-bottom: 20rpx;
}

.card-title {
  font-size: 24rpx;
  font-weight: 600;
  color: #888;
  margin-bottom: 16rpx;
  display: block;
  text-transform: uppercase;
  letter-spacing: 2rpx;
}

.settings-body {
  display: flex;
  flex-direction: column;
}

/* Setting Row */
.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20rpx 0;
  border-bottom: 1rpx solid #f5f5f5;
}

.setting-row:last-child {
  border-bottom: none;
}

.setting-row-danger .row-label {
  color: #e74c3c;
}

.row-active {
  background: rgba(26, 26, 46, 0.03);
  margin: 0 -24rpx;
  padding-left: 24rpx;
  padding-right: 24rpx;
  border-radius: 12rpx;
}

.row-left {
  display: flex;
  align-items: center;
  gap: 16rpx;
}

.row-icon {
  font-size: 32rpx;
  width: 48rpx;
  text-align: center;
}

.row-label {
  font-size: 28rpx;
  color: #333;
}

.row-right {
  display: flex;
  align-items: center;
  gap: 12rpx;
}

.row-value {
  font-size: 26rpx;
  color: #888;
}

.row-arrow {
  font-size: 32rpx;
  color: #ccc;
}

.check-icon {
  font-size: 28rpx;
  color: #1a1a2e;
  font-weight: 700;
}

/* Persona icon */
.persona-icon {
  width: 48rpx;
  height: 48rpx;
  border-radius: 12rpx;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.persona-icon.persona-active {
  background: rgba(26, 26, 46, 0.1);
}

.persona-icon-text {
  font-size: 24rpx;
}

/* Footer */
.footer-brand {
  display: block;
  text-align: center;
  font-size: 24rpx;
  color: #ccc;
  margin-top: 40rpx;
}

/* Auth Panel Modal */
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 999;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.auth-panel {
  width: 100%;
  background: #fff;
  border-radius: 32rpx 32rpx 0 0;
  padding: 32rpx;
  padding-bottom: calc(32rpx + env(safe-area-inset-bottom));
  max-height: 70vh;
  overflow-y: auto;
}

.auth-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24rpx;
}

.auth-title {
  font-size: 32rpx;
  font-weight: 700;
  color: #1a1a2e;
}

.btn-save {
  font-size: 26rpx;
  height: 56rpx;
  line-height: 56rpx;
  padding: 0 32rpx;
  background: #1a1a2e;
  color: #fff;
  border-radius: 12rpx;
  border: none;
}

.btn-save::after { border: none; }
.btn-save[disabled] { background: #ccc; }

.auth-body {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}

.auth-field {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}

.auth-label {
  font-size: 24rpx;
  color: #888;
  font-family: monospace;
}

.auth-input {
  height: 64rpx;
  padding: 0 20rpx;
  background: #f5f5f5;
  border-radius: 12rpx;
  font-size: 28rpx;
}
</style>
