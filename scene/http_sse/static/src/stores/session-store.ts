import { create } from 'zustand';
import { AUTH_KEYS, AUTH_STORAGE_KEY } from '../config';

interface SessionState {
  sessionId: string | null;
  authHeaders: Record<string, string>;
  hasAuth: boolean;

  setSessionId: (id: string) => void;
  clearSession: () => void;
  loadAuth: () => void;
  saveAuth: (headers: Record<string, string>) => void;
  buildAuthHeaders: () => Record<string, string>;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessionId: null,
  authHeaders: {},
  hasAuth: false,

  setSessionId: (id) => set({ sessionId: id }),

  clearSession: () => set({ sessionId: null }),

  loadAuth: () => {
    try {
      const raw = localStorage.getItem(AUTH_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        const headers: Record<string, string> = {};
        for (const k of AUTH_KEYS) {
          if (parsed[k]) headers[k] = parsed[k];
        }
        set({ authHeaders: headers, hasAuth: Object.keys(headers).length > 0 });
      }
    } catch {
      // ignore corrupted storage
    }
  },

  saveAuth: (headers) => {
    const filtered: Record<string, string> = {};
    for (const k of AUTH_KEYS) {
      if (headers[k]) filtered[k] = headers[k];
    }
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(filtered));
    set({ authHeaders: filtered, hasAuth: Object.keys(filtered).length > 0 });
  },

  buildAuthHeaders: () => {
    const h = get().authHeaders;
    const out: Record<string, string> = {};
    for (const k of AUTH_KEYS) {
      if (h[k]) out[k] = h[k];
    }
    return out;
  },
}));
