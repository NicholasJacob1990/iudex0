import { create } from 'zustand';
import apiClient from '@/lib/api-client';

interface OrgMember {
  user_id: string;
  user_name: string;
  user_email: string;
  role: string;
  joined_at: string;
}

interface OrgTeam {
  id: string;
  name: string;
  description: string | null;
  member_count: number;
  created_at: string;
}

interface Organization {
  id: string;
  name: string;
  slug: string;
  plan: string;
  max_members: number;
  member_count: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface OrgState {
  organization: Organization | null;
  members: OrgMember[];
  teams: OrgTeam[];
  isLoading: boolean;
  error: string | null;

  fetchOrganization: () => Promise<void>;
  fetchMembers: () => Promise<void>;
  fetchTeams: () => Promise<void>;
  createOrganization: (data: { name: string; cnpj?: string; oab_section?: string }) => Promise<Organization>;
  inviteMember: (email: string, role?: string) => Promise<void>;
  updateMemberRole: (userId: string, role: string) => Promise<void>;
  removeMember: (userId: string) => Promise<void>;
  createTeam: (data: { name: string; description?: string }) => Promise<void>;
  reset: () => void;
}

export const useOrgStore = create<OrgState>()((set, get) => ({
  organization: null,
  members: [],
  teams: [],
  isLoading: false,
  error: null,

  fetchOrganization: async () => {
    set({ isLoading: true, error: null });
    try {
      const org = await apiClient.getCurrentOrganization();
      set({ organization: org, isLoading: false });
    } catch (error: any) {
      if (error?.response?.status === 404) {
        set({ organization: null, isLoading: false });
      } else {
        set({ error: 'Erro ao carregar organização', isLoading: false });
      }
    }
  },

  fetchMembers: async () => {
    try {
      const members = await apiClient.getOrgMembers();
      set({ members });
    } catch {
      set({ members: [] });
    }
  },

  fetchTeams: async () => {
    try {
      const teams = await apiClient.getOrgTeams();
      set({ teams });
    } catch {
      set({ teams: [] });
    }
  },

  createOrganization: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const org = await apiClient.createOrganization(data);
      set({ organization: org, isLoading: false });
      return org;
    } catch (error: any) {
      set({ error: 'Erro ao criar organização', isLoading: false });
      throw error;
    }
  },

  inviteMember: async (email, role = 'advogado') => {
    await apiClient.inviteMember(email, role);
    await get().fetchMembers();
  },

  updateMemberRole: async (userId, role) => {
    await apiClient.updateMemberRole(userId, role);
    await get().fetchMembers();
  },

  removeMember: async (userId) => {
    await apiClient.removeMember(userId);
    await get().fetchMembers();
  },

  createTeam: async (data) => {
    await apiClient.createTeam(data);
    await get().fetchTeams();
  },

  reset: () => {
    set({ organization: null, members: [], teams: [], isLoading: false, error: null });
  },
}));
