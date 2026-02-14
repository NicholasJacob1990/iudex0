/**
 * Zustand store para dados do e-mail atual.
 *
 * Carrega dados do e-mail selecionado no Outlook via mail-bridge.
 */

import { create } from 'zustand';
import { getCurrentEmailData, type EmailData } from '@/office/mail-bridge';

interface EmailState {
  currentEmail: EmailData | null;
  isLoading: boolean;
  error: string | null;
  loadCurrentEmail: () => Promise<void>;
  clear: () => void;
}

export const useEmailStore = create<EmailState>()((set) => ({
  currentEmail: null,
  isLoading: false,
  error: null,

  loadCurrentEmail: async () => {
    set({ isLoading: true, error: null });
    try {
      const emailData = await getCurrentEmailData();
      set({ currentEmail: emailData, isLoading: false });
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Erro ao carregar e-mail';
      set({ error: message, isLoading: false });
      console.error('[email-store] Erro:', err);
    }
  },

  clear: () => set({ currentEmail: null, error: null }),
}));
