/**
 * Tipos relacionados a usuários e autenticação
 */

export enum UserRole {
  USER = 'USER',
  PREMIUM = 'PREMIUM',
  ADMIN = 'ADMIN',
}

export enum UserPlan {
  FREE = 'FREE',
  INDIVIDUAL = 'INDIVIDUAL',
  PROFESSIONAL = 'PROFESSIONAL',
  ENTERPRISE = 'ENTERPRISE',
}

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  plan: UserPlan;
  avatar?: string;
  institution?: string;
  position?: string;
  oab?: string;
  signature?: string;
  preferences: UserPreferences;
  createdAt: Date;
  updatedAt: Date;
}

export interface UserPreferences {
  theme: 'light' | 'dark' | 'system';
  language: 'pt-BR' | 'en-US';
  writingStyle?: string;
  languageRestrictions?: string[];
  defaultVerbosity: 'concise' | 'balanced' | 'detailed';
  autoSaveInterval: number;
  notificationsEnabled: boolean;
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData extends LoginCredentials {
  name: string;
}

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  plan: UserPlan;
  avatar?: string;
  institution?: string;
  position?: string;
  oab?: string;
  preferences: UserPreferences;
}

