import { create } from 'zustand';

export type H5Tab = 'chat' | 'skills' | 'settings' | 'history' | 'companion';

interface UIState {
  welcomeVisible: boolean;
  authModalOpen: boolean;
  inputValue: string;

  setWelcomeVisible: (v: boolean) => void;
  setAuthModalOpen: (v: boolean) => void;
  setInputValue: (v: string) => void;

  h5ActiveTab: H5Tab;
  h5SettingsSubPage: string | null;
  setH5ActiveTab: (tab: H5Tab) => void;
  setH5SettingsSubPage: (page: string | null) => void;
}

export const useUIStore = create<UIState>((set) => ({
  welcomeVisible: true,
  authModalOpen: false,
  inputValue: '',

  setWelcomeVisible: (v) => set({ welcomeVisible: v }),
  setAuthModalOpen: (v) => set({ authModalOpen: v }),
  setInputValue: (v) => set({ inputValue: v }),

  h5ActiveTab: 'chat',
  h5SettingsSubPage: null,
  setH5ActiveTab: (tab) => set({ h5ActiveTab: tab, h5SettingsSubPage: null }),
  setH5SettingsSubPage: (page) => set({ h5SettingsSubPage: page }),
}));
