/**
 * Theme Store — 移植自 scene/h5/static/src/stores/theme-store.ts
 *
 * 小程序不支持 document.documentElement，主题通过页面 CSS class 实现。
 * 页面根元素根据 themeStore.theme 添加 'theme-dark' / 'theme-light' class。
 */

import { reactive } from 'vue';

const THEME_KEY = 'agent_theme';

function getInitialTheme() {
  try {
    const stored = uni.getStorageSync(THEME_KEY);
    if (stored === 'dark' || stored === 'light') return stored;
  } catch (e) { /* ignore */ }
  // 微信小程序可通过 uni.getSystemInfoSync 获取系统主题
  try {
    const sysInfo = uni.getSystemInfoSync();
    if (sysInfo.theme === 'dark') return 'dark';
  } catch (e) { /* ignore */ }
  return 'light';
}

export const themeStore = reactive({
  /** @type {'light'|'dark'} */
  theme: getInitialTheme(),

  toggleTheme() {
    const next = this.theme === 'light' ? 'dark' : 'light';
    this.setTheme(next);
  },

  setTheme(theme) {
    try {
      uni.setStorageSync(THEME_KEY, theme);
    } catch (e) { /* ignore */ }
    this.theme = theme;
  },

  /** 是否为暗色模式 */
  get isDark() {
    return this.theme === 'dark';
  },
});
