import { create } from 'zustand';

const SIDEBAR_COLLAPSED_KEY = 'sidebar_collapsed';

function getInitialCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true';
  } catch {
    return false;
  }
}

export type Page = 'chat' | 'skills' | 'connectors' | 'experts';

interface UIState {
  activePage: Page;
  welcomeVisible: boolean;
  authModalOpen: boolean;
  inputValue: string;
  sidebarCollapsed: boolean;

  setActivePage: (v: Page) => void;
  setWelcomeVisible: (v: boolean) => void;
  setAuthModalOpen: (v: boolean) => void;
  setInputValue: (v: string) => void;
  toggleSidebar: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  activePage: 'chat',
  welcomeVisible: true,
  authModalOpen: false,
  inputValue: '',
  sidebarCollapsed: getInitialCollapsed(),

  setActivePage: (v) => set({ activePage: v }),
  setWelcomeVisible: (v) => set({ welcomeVisible: v }),
  setAuthModalOpen: (v) => set({ authModalOpen: v }),
  setInputValue: (v) => set({ inputValue: v }),
  toggleSidebar: () =>
    set((s) => {
      const next = !s.sidebarCollapsed;
      try {
        localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
      } catch {
        // ignore
      }
      return { sidebarCollapsed: next };
    }),
}));
