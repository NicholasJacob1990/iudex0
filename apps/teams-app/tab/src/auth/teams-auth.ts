import { app, authentication } from '@microsoft/teams-js';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api';

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: {
    id: string;
    email: string;
    name: string;
    role: string;
    plan: string;
    account_type: string;
    organization_id?: string | null;
    created_at: string;
  };
}

export async function getTeamsToken(): Promise<string> {
  await app.initialize();
  const token = await authentication.getAuthToken({
    resources: [import.meta.env.VITE_AZURE_CLIENT_ID],
    silent: true,
  });
  return token;
}

export async function loginWithTeamsSSO(): Promise<AuthResponse> {
  const teamsToken = await getTeamsToken();
  const response = await fetch(`${API_URL}/auth/teams-sso`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ teams_token: teamsToken }),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Erro desconhecido');
    throw new Error(`Erro ao autenticar via Teams SSO: ${response.status} - ${errorText}`);
  }

  return response.json();
}
