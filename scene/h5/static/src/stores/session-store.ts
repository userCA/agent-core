import { create } from 'zustand';
import { fetchSessions, fetchPersonas, type PersonaInfo } from '../api/client';
import { useToastStore } from './toast-store';

export type { PersonaInfo };
import { AUTH_KEYS, AUTH_STORAGE_KEY } from '../config';

const KNOWN_UIDS_KEY = 'agent_known_uids';

function loadKnownUids(): string[] {
  try {
    const raw = localStorage.getItem(KNOWN_UIDS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export interface SessionSummary {
  session_id: string;
  created_at: string;
  entry_count: number;
  title?: string;
}

interface SessionState {
  sessionId: string | null;
  authHeaders: Record<string, string>;
  hasAuth: boolean;
  knownUids: string[];
  sessions: SessionSummary[];
  sessionsLoading: boolean;
  personas: PersonaInfo[];
  personasLoading: boolean;
  personaId: string | null;

  setSessionId: (id: string | null) => void;
  clearSession: () => void;
  loadAuth: () => void;
  saveAuth: (headers: Record<string, string>) => void;
  clearAuth: () => void;
  buildAuthHeaders: () => Record<string, string>;
  registerUid: (uid: string) => void;
  loadSessions: () => Promise<void>;
  loadPersonas: () => Promise<void>;
  setPersonaId: (id: string | null) => void;
  createSession: () => void;
  switchSession: (id: string) => void;
  removeSession: (id: string) => void;
}

function formatSessionTitle(sessions: SessionSummary[]): SessionSummary[] {
  return sessions.map((s, idx) => ({
    ...s,
    title: s.title || `会话 ${sessions.length - idx}`,
  }));
}

const PERSONA_STORAGE_KEY = 'agent_persona_id';

function getInitialPersonaId(): string | null {
  try {
    return localStorage.getItem(PERSONA_STORAGE_KEY);
  } catch {
    return null;
  }
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessionId: null,
  authHeaders: {},
  hasAuth: false,
  knownUids: loadKnownUids(),
  sessions: [],
  sessionsLoading: false,
  personas: [],
  personasLoading: false,
  personaId: getInitialPersonaId(),

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

  clearAuth: () => {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    set({ authHeaders: {}, hasAuth: false, sessionId: null });
  },

  registerUid: (uid) => {
    const current = get().knownUids;
    if (current.includes(uid)) return;
    const next = [uid, ...current].slice(0, 20);
    localStorage.setItem(KNOWN_UIDS_KEY, JSON.stringify(next));
    set({ knownUids: next });
  },

  buildAuthHeaders: () => {
    const h = get().authHeaders;
    const out: Record<string, string> = {};
    for (const k of AUTH_KEYS) {
      if (h[k]) out[k] = h[k];
    }
    return out;
  },

  loadSessions: async () => {
    set({ sessionsLoading: true });
    try {
      const raw = await fetchSessions();
      const sessions = formatSessionTitle(
        raw.map((s) => ({
          session_id: s.session_id,
          created_at: s.created_at,
          entry_count: s.entry_count,
          title: s.title,
        }))
      );
      set({ sessions });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '加载会话失败';
      useToastStore.getState().addToast(msg, 'error');
    } finally {
      set({ sessionsLoading: false });
    }
  },

  loadPersonas: async () => {
    set({ personasLoading: true });
    try {
      const data = await fetchPersonas();
      set({ personas: data });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '加载专家失败';
      useToastStore.getState().addToast(msg, 'error');
    } finally {
      set({ personasLoading: false });
    }
  },

  setPersonaId: (id) => {
    try {
      if (id) localStorage.setItem(PERSONA_STORAGE_KEY, id);
      else localStorage.removeItem(PERSONA_STORAGE_KEY);
    } catch {
      // ignore
    }
    set({ personaId: id });
  },

  createSession: () => {
    set({ sessionId: null });
  },

  switchSession: (id) => {
    set({ sessionId: id });
    // Load historical messages for this session
    import('./chat-store').then(({ useChatStore }) => {
      const cs = useChatStore.getState();
      cs.loadSessionMessages(id);
    }).catch(() => {});
  },

  removeSession: (id) => {
    set((state) => ({
      sessions: state.sessions.filter((s) => s.session_id !== id),
      sessionId: state.sessionId === id ? null : state.sessionId,
    }));
  },
}));
