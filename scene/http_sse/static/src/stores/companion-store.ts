import { create } from 'zustand';
import type { CompanionMood } from '../components/companion/CompanionSprite';

export interface CompanionBones {
  uid: string;
  species: string;
  rarity: string;
  eye: string;
  ear: string;
  accent: string;
  shiny: boolean;
  color: string;
  stats: Record<string, number>;
}

interface CompanionState {
  mood: CompanionMood;
  muted: boolean;
  bones: CompanionBones | null;
  revealed: boolean;

  setMood: (mood: CompanionMood) => void;
  toggleMuted: () => void;
  reveal: (uid: string) => Promise<void>;
  reset: () => void;
}

export const useCompanionStore = create<CompanionState>((set) => ({
  mood: 'sleeping',
  muted: false,
  bones: null,
  revealed: false,

  setMood: (mood) => set({ mood }),
  toggleMuted: () => set((s) => ({ muted: !s.muted })),

  reveal: async (uid) => {
    try {
      const res = await fetch(`/api/companion/${encodeURIComponent(uid)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const bones: CompanionBones = await res.json();
      set({ bones, revealed: true, mood: 'happy' });
    } catch {
      // API unavailable — still show happy mood without bones
      set({ revealed: true, mood: 'happy' });
    }
  },

  reset: () => set({ bones: null, revealed: false, mood: 'sleeping' }),
}));
