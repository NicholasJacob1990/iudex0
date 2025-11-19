import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type TabType = 'home' | 'minuta' | 'documents' | 'models' | 'legislation' | 'jurisprudence';

interface UIState {
  activeTab: TabType;
  sidebarOpen: boolean;
  theme: 'light' | 'dark' | 'system';
  setActiveTab: (tab: TabType) => void;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      activeTab: 'home',
      sidebarOpen: true,
      theme: 'system',

      setActiveTab: (tab) => set({ activeTab: tab }),

      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

      setSidebarOpen: (open) => set({ sidebarOpen: open }),

      setTheme: (theme) => set({ theme }),
    }),
    {
      name: 'ui-storage',
    }
  )
);

