import { create } from 'zustand';
import type { CompanionMood } from '../components/companion/CompanionSprite';

interface CompanionState {
  mood: CompanionMood;
  muted: boolean;
  setMood: (mood: CompanionMood) => void;
  toggleMuted: () => void;
}

export const useCompanionStore = create<CompanionState>((set) => ({
  mood: 'sleeping',
  muted: false,
  setMood: (mood) => set({ mood }),
  toggleMuted: () => set((s) => ({ muted: !s.muted })),
}));
