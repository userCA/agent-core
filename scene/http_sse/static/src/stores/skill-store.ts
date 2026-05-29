import { create } from 'zustand';
import { fetchCapabilities } from '../api/client';

export interface SkillInfo {
  name: string;
  description: string;
}

interface SkillState {
  skills: SkillInfo[];
  tools: string[];
  loading: boolean;

  loadCapabilities: () => Promise<void>;
}

export const useSkillStore = create<SkillState>((set) => ({
  skills: [],
  tools: [],
  loading: false,

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
}));
