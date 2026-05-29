import { create } from 'zustand';

const SIDEBAR_COLLAPSED_KEY = 'sidebar_collapsed';

function getInitialCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true';
  } catch {
    return false;
  }
}

interface UIState {
  welcomeVisible: boolean;
  authModalOpen: boolean;
  connectorPanelOpen: boolean;
  inputValue: string;
  sidebarCollapsed: boolean;

  setWelcomeVisible: (v: boolean) => void;
  setAuthModalOpen: (v: boolean) => void;
  setConnectorPanelOpen: (v: boolean) => void;
  setInputValue: (v: string) => void;
  toggleSidebar: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  welcomeVisible: true,
  authModalOpen: false,
  connectorPanelOpen: false,
  inputValue: '',
  sidebarCollapsed: getInitialCollapsed(),

  setWelcomeVisible: (v) => set({ welcomeVisible: v }),
  setAuthModalOpen: (v) => set({ authModalOpen: v }),
  setConnectorPanelOpen: (v) => set({ connectorPanelOpen: v }),
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
