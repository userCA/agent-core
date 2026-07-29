/**
 * Session Store — 移植自 scene/h5/static/src/stores/session-store.ts
 *
 * 使用 Vue 3 reactive 替代 Zustand，管理认证、会话 ID、已知 UID 等状态。
 * 小程序使用 uni.setStorageSync / uni.getStorageSync 替代 localStorage。
 */

import { reactive } from 'vue';
import { AUTH_KEYS, AUTH_STORAGE_KEY, KNOWN_UIDS_KEY } from '../api/config.js';
import { fetchSessions as apiFetchSessions, deleteSession as apiDeleteSession, fetchPersonas as apiFetchPersonas } from '../api/client.js';

// ---- 辅助函数 ----

function loadAuthFromStorage() {
  try {
    const raw = uni.getStorageSync(AUTH_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      const headers = {};
      for (const k of AUTH_KEYS) {
        if (parsed[k]) headers[k] = parsed[k];
      }
      return headers;
    }
  } catch (e) {
    // ignore corrupted storage
  }
  return {};
}

function loadKnownUids() {
  try {
    const raw = uni.getStorageSync(KNOWN_UIDS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}

// ---- Store 定义 ----

const initialAuthHeaders = loadAuthFromStorage();

export const sessionStore = reactive({
  sessionId: null,
  authHeaders: { ...initialAuthHeaders },
  hasAuth: Object.keys(initialAuthHeaders).length > 0,
  knownUids: loadKnownUids(),
  personaId: null,
  /** @type {Array<{id: string, name: string, description: string}>} */
  personas: [],
  /** @type {Array<{session_id: string, title: string, entry_count: number, created_at: string}>} */
  sessions: [],
  sessionsLoading: false,

  // ---- Actions ----

  setSessionId(id) {
    this.sessionId = id;
  },

  clearSession() {
    this.sessionId = null;
  },

  /** 从本地存储加载认证信息 */
  loadAuth() {
    const headers = loadAuthFromStorage();
    this.authHeaders = headers;
    this.hasAuth = Object.keys(headers).length > 0;
  },

  /** 保存认证信息并持久化 */
  saveAuth(headers) {
    const filtered = {};
    for (const k of AUTH_KEYS) {
      if (headers[k]) filtered[k] = headers[k];
    }
    uni.setStorageSync(AUTH_STORAGE_KEY, JSON.stringify(filtered));
    this.authHeaders = filtered;
    this.hasAuth = Object.keys(filtered).length > 0;
  },

  /** 清除认证信息 */
  clearAuth() {
    uni.removeStorageSync(AUTH_STORAGE_KEY);
    this.authHeaders = {};
    this.hasAuth = false;
    this.sessionId = null;
  },

  /** 构造鉴权请求头 */
  buildAuthHeaders() {
    const out = {};
    for (const k of AUTH_KEYS) {
      if (this.authHeaders[k]) out[k] = this.authHeaders[k];
    }
    return out;
  },

  /** 注册 UID 到已知列表 */
  registerUid(uid) {
    if (this.knownUids.includes(uid)) return;
    const next = [uid, ...this.knownUids].slice(0, 20);
    uni.setStorageSync(KNOWN_UIDS_KEY, JSON.stringify(next));
    this.knownUids = next;
  },

  /** 创建新会话（清空 sessionId） */
  createSession() {
    this.sessionId = null;
  },

  /** 切换到指定会话 */
  switchSession(id) {
    this.sessionId = id;
  },

  /** 设置 Persona ID */
  setPersonaId(id) {
    this.personaId = id;
  },

  /** 从后端加载 Persona 列表 */
  async loadPersonas() {
    try {
      this.personas = await apiFetchPersonas();
    } catch (e) {
      console.warn('[session] loadPersonas failed:', e);
    }
  },

  /** 从后端加载会话列表 */
  async loadSessions() {
    this.sessionsLoading = true;
    try {
      const list = await apiFetchSessions();
      this.sessions = list;
    } catch (e) {
      console.warn('[session] loadSessions failed:', e);
    } finally {
      this.sessionsLoading = false;
    }
  },

  /** 从本地列表移除指定会话 */
  removeSession(id) {
    this.sessions = this.sessions.filter((s) => s.session_id !== id);
    if (this.sessionId === id) {
      this.sessionId = null;
    }
  },

  /** 删除会话（后端 + 本地） */
  async deleteSession(id) {
    await apiDeleteSession(id);
    this.removeSession(id);
  },
});
