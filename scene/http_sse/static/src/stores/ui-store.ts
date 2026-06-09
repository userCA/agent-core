import { create } from 'zustand';

const SIDEBAR_COLLAPSED_KEY = 'sidebar_collapsed';

function getInitialCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true';
  } catch {
    return false;
  }
}

export type Page = 'chat' | 'skills' | 'connectors' | 'experts' | 'knowledge' | 'channels';
export type H5Tab = 'chat' | 'skills' | 'settings' | 'history';

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

  h5ActiveTab: H5Tab;
  h5SettingsSubPage: string | null;
  setH5ActiveTab: (tab: H5Tab) => void;
  setH5SettingsSubPage: (page: string | null) => void;
}

function getInitialPage(): Page {
  try {
    const params = new URLSearchParams(window.location.search);
    const page = params.get('page') as Page;
    if (page && ['chat', 'skills', 'connectors', 'experts', 'knowledge'].includes(page)) {
      return page;
    }
  } catch {
    // ignore
  }
  return 'chat';
}

function syncPageToURL(page: Page) {
  try {
    const url = new URL(window.location.href);
    if (page === 'chat') {
      url.searchParams.delete('page');
    } else {
      url.searchParams.set('page', page);
    }
    window.history.replaceState({ page }, '', url.toString());
  } catch {
    // ignore
  }
}

export const useUIStore = create<UIState>((set) => ({
  activePage: getInitialPage(),
  welcomeVisible: true,
  authModalOpen: false,
  inputValue: '',
  sidebarCollapsed: getInitialCollapsed(),

  setActivePage: (v) => {
    syncPageToURL(v);
    set({ activePage: v });
  },
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

  h5ActiveTab: 'chat',
  h5SettingsSubPage: null,
  setH5ActiveTab: (tab) => set({ h5ActiveTab: tab, h5SettingsSubPage: null }),
  setH5SettingsSubPage: (page) => set({ h5SettingsSubPage: page }),
}));
