import { create } from 'zustand';

export interface ModelOption {
  provider: string;
  model: string;
  label: string;
  desc: string;
}

interface ModelState {
  models: ModelOption[];
  currentProvider: string;
  currentModel: string;
  loadModels: () => Promise<void>;
  selectModel: (provider: string, model: string) => void;
}

const DEFAULT: ModelOption = { provider: 'openai', model: 'gpt-4o', label: 'GPT-4o', desc: '' };

export const useModelStore = create<ModelState>((set, get) => ({
  models: [DEFAULT],
  currentProvider: DEFAULT.provider,
  currentModel: DEFAULT.model,

  loadModels: async () => {
    try {
      const resp = await fetch('/models');
      if (!resp.ok) return;
      const data = await resp.json();
      set({
        models: data.available || [DEFAULT],
        currentProvider: data.current?.provider || DEFAULT.provider,
        currentModel: data.current?.model || DEFAULT.model,
      });
    } catch {
      // Use defaults
    }
  },

  selectModel: (provider, model) => {
    set({ currentProvider: provider, currentModel: model });
  },
}));
