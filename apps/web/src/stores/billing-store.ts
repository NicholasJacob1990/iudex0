import { create } from 'zustand';
import apiClient from '@/lib/api-client';

export type BillingConfig = Record<string, any>;

interface BillingState {
  billing: BillingConfig | null;
  isLoading: boolean;
  loaded: boolean;
  fetchBilling: () => Promise<void>;
}

export const useBillingStore = create<BillingState>((set, get) => ({
  billing: null,
  isLoading: false,
  loaded: false,

  fetchBilling: async () => {
    if (get().loaded || get().isLoading) return;
    set({ isLoading: true });
    try {
      const billing = await apiClient.getBillingConfig();
      set({ billing: billing || null, loaded: true, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },
}));
