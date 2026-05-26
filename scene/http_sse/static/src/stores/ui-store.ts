import { create } from 'zustand';

interface UIState {
  welcomeVisible: boolean;
  authModalOpen: boolean;
  inputValue: string;

  setWelcomeVisible: (v: boolean) => void;
  setAuthModalOpen: (v: boolean) => void;
  setInputValue: (v: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  welcomeVisible: true,
  authModalOpen: false,
  inputValue: '',

  setWelcomeVisible: (v) => set({ welcomeVisible: v }),
  setAuthModalOpen: (v) => set({ authModalOpen: v }),
  setInputValue: (v) => set({ inputValue: v }),
}));
