import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type TabType = 'home' | 'minuta' | 'documents' | 'models' | 'legislation' | 'jurisprudence';
type SidebarState = 'expanded' | 'collapsed' | 'hidden';

interface UIState {
  activeTab: TabType;
  sidebarState: SidebarState;
  theme: 'light' | 'dark' | 'system';
  setActiveTab: (tab: TabType) => void;
  toggleSidebar: () => void;
  toggleSidebarCollapse: () => void;
  setSidebarState: (state: SidebarState) => void;
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      activeTab: 'home',
      sidebarState: 'expanded',
      theme: 'system',

      setActiveTab: (tab) => set({ activeTab: tab }),

      toggleSidebar: () =>
        set((state) => ({
          sidebarState: state.sidebarState === 'hidden' ? 'expanded' : 'hidden',
        })),

      toggleSidebarCollapse: () =>
        set((state) => ({
          sidebarState: state.sidebarState === 'collapsed' ? 'expanded' : 'collapsed',
        })),

      setSidebarState: (state) => set({ sidebarState: state }),

      setTheme: (theme) => set({ theme }),
    }),
    {
      name: 'ui-storage',
    }
  )
);
