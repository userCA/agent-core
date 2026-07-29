<script>
import { sessionStore } from './stores/session.js';

export default {
  onLaunch() {
    console.log('[App] Launch');
    // 加载本地存储的认证信息
    sessionStore.loadAuth();
    // 如果未登录，跳转到登录页
    if (!sessionStore.hasAuth) {
      uni.redirectTo({ url: '/pages/login/index' });
    }
  },
  onShow() {
    console.log('[App] Show');
  },
  onHide() {
    console.log('[App] Hide');
  },
};
</script>

<style>
/* ---- 水墨风 CSS Token ---- */
page {
  /* 亮色主题（默认） */
  --canvas: #f5f5f5;
  --surface: #ffffff;
  --surface-card: #ffffff;
  --ink: #1a1a2e;
  --ink-light: #333333;
  --ash: #888888;
  --mist: #e0e0e0;
  --accent: #1a1a2e;
  --accent-light: #3a3a5e;
  --danger: #e74c3c;
  --success: #27ae60;
  --border: #eeeeee;
  --shadow: rgba(0, 0, 0, 0.06);

  background-color: var(--canvas);
  font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei',
    -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
    'Helvetica Neue', Arial, sans-serif;
  font-size: 28rpx;
  color: var(--ink-light);
  height: 100%;
}

/* 暗色主题（通过页面 class 激活） */
page.theme-dark {
  --canvas: #1a1a2e;
  --surface: #2a2a40;
  --surface-card: #2a2a40;
  --ink: #e0e0e0;
  --ink-light: #cccccc;
  --ash: #888888;
  --mist: #3a3a50;
  --accent: #6c7ae0;
  --accent-light: #8b96f0;
  --danger: #e74c3c;
  --success: #2ecc71;
  --border: #3a3a50;
  --shadow: rgba(0, 0, 0, 0.2);
}

/* 安全区域适配 */
.safe-bottom {
  padding-bottom: env(safe-area-inset-bottom);
}

/* 全局链接 */
rich-text a {
  color: var(--accent);
}
</style>
