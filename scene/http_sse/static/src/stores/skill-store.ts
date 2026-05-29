import { create } from 'zustand';
import { fetchCapabilities } from '../api/client';

export interface SkillInfo {
  name: string;
  description: string;
}

const SKILL_ENABLED_KEY = 'agent_skill_enabled';

function loadEnabled(): Set<string> {
  try {
    const raw = localStorage.getItem(SKILL_ENABLED_KEY);
    if (raw) return new Set(JSON.parse(raw));
  } catch { /* ignore */ }
  return new Set();
}

function saveEnabled(enabled: Set<string>) {
  try {
    localStorage.setItem(SKILL_ENABLED_KEY, JSON.stringify([...enabled]));
  } catch { /* ignore */ }
}

interface SkillState {
  skills: SkillInfo[];
  tools: string[];
  loading: boolean;
  enabled: Set<string>;

  loadCapabilities: () => Promise<void>;
  toggleSkill: (name: string) => void;
  isEnabled: (name: string) => boolean;
}

export const useSkillStore = create<SkillState>((set, get) => ({
  skills: [],
  tools: [],
  loading: false,
  enabled: loadEnabled(),

  loadCapabilities: async () => {
    set({ loading: true });
    try {
      const caps = await fetchCapabilities();
      set({ skills: caps.skills, tools: caps.tools });
    } catch {
      // ignore
    } finally {
      set({ loading: false });
    }
  },

  toggleSkill: (name) => {
    const next = new Set(get().enabled);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    saveEnabled(next);
    set({ enabled: next });
  },

  isEnabled: (name) => get().enabled.has(name),
}));
