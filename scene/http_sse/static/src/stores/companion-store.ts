/**
 * Companion Store — thin cache of backend state.
 *
 * Boundary rule: frontend NEVER determines mood locally.
 * mood derives from emotion.frontend_mood (set by setEmotion),
 * or defaults to 'sleeping' before first SSE event.
 *
 * Backend is the sole source of truth for:
 *   - emotion state (via SSE companion events)
 *   - deterministic bones (via GET /api/companion/{uid})
 */
import { create } from 'zustand';
import type { CompanionMood, BreedId } from '../components/companion/CompanionSprite';

// -- data contracts (mirrors Python CompanionBones + SSE companion event) --

export interface CompanionBones {
  uid: string;
  breed: BreedId;
  rarity: string;
  eye: string;
  ear: string;
  accent: string;
  hat: string;
  quirk: string;
  shiny: boolean;
  color: string;
  stats: Record<string, number>;
  // filled after hatch
  name?: string;
  personality?: string;
  hatched_at?: number;
}

export interface CompanionEmotion {
  emotion: string;
  eye_override: string | null;
  frontend_mood: CompanionMood;
}

// -- store --

export interface CompanionBubble {
  text: string;
  ttl_ms: number;
}

interface CompanionState {
  /** Derived from emotion.frontend_mood, or 'sleeping' before SSE connects. */
  mood: CompanionMood;
  muted: boolean;
  bones: CompanionBones | null;
  emotion: CompanionEmotion | null;
  bubble: CompanionBubble | null;
  revealed: boolean;

  /** Called by SSE handler when backend pushes companion event. */
  setEmotion: (emotion: CompanionEmotion) => void;
  /** Called by SSE handler when backend pushes a bubble. */
  setBubble: (bubble: CompanionBubble | null) => void;
  toggleMuted: () => void;
  /** Fetch bones from backend and set revealed=true. */
  reveal: (uid: string) => Promise<void>;
  /** Reset all state (e.g. user logs out / clears uid). */
  reset: () => void;
}

export const useCompanionStore = create<CompanionState>((set) => ({
  mood: 'sleeping',
  muted: false,
  bones: null,
  emotion: null,
  bubble: null,
  revealed: false,

  setEmotion: (emotion) => set({ emotion, mood: emotion.frontend_mood }),
  setBubble: (bubble) => set({ bubble }),

  toggleMuted: () => set((s) => ({ muted: !s.muted })),

  reveal: async (uid) => {
    try {
      // hatch first: generates name + personality
      const hatchRes = await fetch(`/api/companion/${encodeURIComponent(uid)}/hatch`, { method: 'POST' });
      if (hatchRes.ok) {
        const data: CompanionBones = await hatchRes.json();
        set({ bones: data, revealed: true });
        return;
      }
    } catch { /* fallthrough to bones-only */ }
    try {
      const res = await fetch(`/api/companion/${encodeURIComponent(uid)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const bones: CompanionBones = await res.json();
      set({ bones, revealed: true });
    } catch {
      set({ revealed: true });
    }
  },

  reset: () => set({ bones: null, emotion: null, revealed: false, mood: 'sleeping' }),
}));
