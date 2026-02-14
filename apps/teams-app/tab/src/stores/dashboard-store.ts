import { create } from 'zustand';
import {
  getWorkflows,
  getNotifications,
  type Workflow,
  type Notification,
} from '@/api/client';

interface DashboardState {
  // Workflows
  workflows: Workflow[];
  workflowsLoading: boolean;
  workflowsError: string | null;
  workflowsTotal: number;

  // Notifications
  notifications: Notification[];
  notificationsLoading: boolean;

  // Actions
  fetchWorkflows: (limit?: number) => Promise<void>;
  fetchNotifications: (limit?: number) => Promise<void>;
  refreshAll: () => Promise<void>;
}

export const useDashboardStore = create<DashboardState>()((set) => ({
  // Workflows
  workflows: [],
  workflowsLoading: false,
  workflowsError: null,
  workflowsTotal: 0,

  // Notifications
  notifications: [],
  notificationsLoading: false,

  // Actions
  fetchWorkflows: async (limit = 20) => {
    set({ workflowsLoading: true, workflowsError: null });
    try {
      const response = await getWorkflows(limit);
      set({
        workflows: response.items,
        workflowsTotal: response.total,
        workflowsLoading: false,
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Erro ao carregar workflows';
      set({ workflowsError: message, workflowsLoading: false });
    }
  },

  fetchNotifications: async (limit = 10) => {
    set({ notificationsLoading: true });
    try {
      const notifications = await getNotifications(limit);
      set({ notifications, notificationsLoading: false });
    } catch {
      set({ notificationsLoading: false });
    }
  },

  refreshAll: async () => {
    const state = useDashboardStore.getState();
    await Promise.all([
      state.fetchWorkflows(),
      state.fetchNotifications(),
    ]);
  },
}));
