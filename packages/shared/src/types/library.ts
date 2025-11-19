/**
 * Tipos relacionados à biblioteca e recursos salvos
 */

export enum LibraryItemType {
  DOCUMENT = 'DOCUMENT',
  MODEL = 'MODEL',
  PROMPT = 'PROMPT',
  JURISPRUDENCE = 'JURISPRUDENCE',
  LEGISLATION = 'LEGISLATION',
  LIBRARIAN = 'LIBRARIAN',
}

export interface LibraryItem {
  id: string;
  userId: string;
  type: LibraryItemType;
  name: string;
  description?: string;
  icon?: string;
  tags: string[];
  folderId?: string;
  resourceId: string; // ID do recurso original
  isShared: boolean;
  sharedWith: SharedPermission[];
  createdAt: Date;
  updatedAt: Date;
}

export interface Folder {
  id: string;
  userId: string;
  name: string;
  description?: string;
  parentId?: string;
  type: LibraryItemType;
  icon?: string;
  color?: string;
  isShared: boolean;
  createdAt: Date;
  updatedAt: Date;
}

export interface Librarian {
  id: string;
  userId: string;
  name: string;
  description: string;
  icon?: string;
  resources: LibrarianResource[];
  isShared: boolean;
  sharedWith: SharedPermission[];
  createdAt: Date;
  updatedAt: Date;
}

export interface LibrarianResource {
  type: LibraryItemType;
  resourceId: string;
}

export enum SharePermission {
  VIEW = 'VIEW',
  EDIT = 'EDIT',
  SHARE = 'SHARE',
}

export interface SharedPermission {
  userId?: string;
  groupId?: string;
  permission: SharePermission;
  autoAccept: boolean;
  acceptedAt?: Date;
}

export interface ShareGroup {
  id: string;
  name: string;
  description?: string;
  ownerId: string;
  members: string[]; // User IDs
  createdAt: Date;
  updatedAt: Date;
}

export interface ShareInvite {
  id: string;
  fromUserId: string;
  toUserId: string;
  resourceType: LibraryItemType;
  resourceId: string;
  permission: SharePermission;
  status: 'PENDING' | 'ACCEPTED' | 'REJECTED';
  createdAt: Date;
  respondedAt?: Date;
}

export interface SavedPrompt {
  id: string;
  userId: string;
  name: string;
  description?: string;
  content: string;
  category?: string;
  tags: string[];
  isPublic: boolean;
  usageCount: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface QuickAction {
  id: string;
  userId: string;
  name: string;
  description: string;
  prompt: string;
  icon?: string;
  color?: string;
  contexts: LibraryItemType[];
  isGlobal: boolean;
  createdAt: Date;
  updatedAt: Date;
}

