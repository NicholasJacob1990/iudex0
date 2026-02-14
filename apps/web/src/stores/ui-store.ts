import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type TabType = 'home' | 'minuta' | 'documents' | 'models' | 'legislation' | 'jurisprudence';
type SidebarState = 'expanded' | 'collapsed' | 'hidden';

type SidebarTheme = 'light' | 'dark';
/** layered = input/canvas default white · blended = lighter tint · inset = darker tint · uniform = same color */
export type TintMode = 'layered' | 'blended' | 'inset' | 'uniform';

const LEGACY_DEFAULT_TINT = 30;
// Match the first pre-stops visual baseline:
// light -> pure white, dark -> near-black base (#0a0a0a).
export const DEFAULT_CHAT_BG_TINT_LIGHT = 100;
export const DEFAULT_CHAT_BG_TINT_DARK = 9;
export const DEFAULT_TINT_MODE: TintMode = 'layered';

function clampTint(value: number): number {
  return Math.max(0, Math.min(100, value));
}

interface UIState {
  activeTab: TabType;
  sidebarState: SidebarState;
  sidebarTheme: SidebarTheme;
  /** When true, sidebar theme follows the page theme automatically */
  sidebarThemeSynced: boolean;
  theme: 'light' | 'dark' | 'system';
  /** Background tint for light mode: 0 = neutral, 100 = blue */
  chatBgTintLight: number;
  /** Background tint for dark mode: 0 = neutral, 100 = light gray */
  chatBgTintDark: number;
  /** Tint blending mode: layered | blended | inset | uniform */
  tintMode: TintMode;
  setActiveTab: (tab: TabType) => void;
  toggleSidebar: () => void;
  toggleSidebarCollapse: () => void;
  setSidebarState: (state: SidebarState) => void;
  setSidebarTheme: (theme: SidebarTheme) => void;
  /** Manually toggle sidebar theme — re-syncs if result matches page theme */
  toggleSidebarTheme: (pageTheme?: SidebarTheme) => void;
  /** Sync sidebar theme to match page theme (only when synced) */
  syncSidebarTheme: (pageTheme: SidebarTheme) => void;
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
  setChatBgTintLight: (tint: number) => void;
  setChatBgTintDark: (tint: number) => void;
  setTintMode: (mode: TintMode) => void;
  cycleTintMode: () => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      activeTab: 'home',
      sidebarState: 'expanded',
      sidebarTheme: 'dark',
      sidebarThemeSynced: true,
      theme: 'system',
      chatBgTintLight: DEFAULT_CHAT_BG_TINT_LIGHT,
      chatBgTintDark: DEFAULT_CHAT_BG_TINT_DARK,
      tintMode: DEFAULT_TINT_MODE,

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

      setSidebarTheme: (theme) => set({ sidebarTheme: theme }),
      toggleSidebarTheme: (pageTheme) =>
        set((state) => {
          const next: SidebarTheme = state.sidebarTheme === 'dark' ? 'light' : 'dark';
          return {
            sidebarTheme: next,
            sidebarThemeSynced: pageTheme ? next === pageTheme : false,
          };
        }),
      syncSidebarTheme: (pageTheme) =>
        set((state) => (state.sidebarThemeSynced ? { sidebarTheme: pageTheme } : {})),

      setTheme: (theme) => set({ theme }),
      setChatBgTintLight: (tint) => set({ chatBgTintLight: clampTint(tint) }),
      setChatBgTintDark: (tint) => set({ chatBgTintDark: clampTint(tint) }),
      setTintMode: (mode) => set({ tintMode: mode }),
      cycleTintMode: () =>
        set((state) => {
          const order: TintMode[] = ['layered', 'blended', 'inset', 'uniform'];
          const idx = order.indexOf(state.tintMode);
          return { tintMode: order[(idx + 1) % order.length] };
        }),
    }),
    {
      name: 'ui-storage',
      merge: (persisted, current) => ({
        ...current,
        ...(persisted as Partial<UIState>),
        // Ensure new fields default correctly for pre-existing persisted stores
        sidebarThemeSynced: (persisted as any)?.sidebarThemeSynced ?? true,
        chatBgTintLight: (() => {
          const persistedTint = (persisted as any)?.chatBgTintLight;
          if (persistedTint == null || persistedTint === LEGACY_DEFAULT_TINT) {
            return DEFAULT_CHAT_BG_TINT_LIGHT;
          }
          return clampTint(persistedTint);
        })(),
        chatBgTintDark: (() => {
          const persistedTint = (persisted as any)?.chatBgTintDark;
          if (persistedTint == null || persistedTint === LEGACY_DEFAULT_TINT) {
            return DEFAULT_CHAT_BG_TINT_DARK;
          }
          return clampTint(persistedTint);
        })(),
        tintMode: (() => {
          const p = persisted as any;
          // Migrate from old 3-state or boolean
          if (p?.tintMode === 'uniform') return 'uniform' as TintMode;
          if (p?.tintMode === 'blended') return 'blended' as TintMode;
          if (p?.tintMode === 'inset') return 'inset' as TintMode;
          if (p?.tintHomogenized === true) return 'uniform' as TintMode;
          return DEFAULT_TINT_MODE;
        })(),
      }),
    }
  )
);
