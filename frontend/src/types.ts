import { SourceChunk } from './api.js';

export type Role = 'user' | 'assistant' | 'context';

export type NoteType = 'text' | 'link' | 'code' | 'media';

export type TabFilter = 'all' | 'highlight' | 'link' | 'media';

export type GlassTheme = 'frosted-glass' | 'crystal-clean' | 'slate-glass' | 'dark-frosted';

export type RequestStatus = 'idle' | 'checking' | 'loading';

export type BackendStatus = 'unknown' | 'ready' | 'unavailable' | 'index_not_ready';

export interface ChatMessage {
  id: string;
  role: Role;
  text: string;
  label?: string;
  highlightedText?: string;
  timestamp: number;
  sources?: SourceChunk[];
  standaloneQuestion?: string;
}

export interface Note {
  id: string;
  type: NoteType;
  title?: string;
  content: string;
  url?: string;
  imageUrl?: string;
  isCode?: boolean;
  highlighted?: boolean;
  createdAt: number;
}

export interface ChatThread {
  id: string;
  title: string;
  meta: string;
  messageCount: number;
  updatedAt: number;
}

export interface AppState {
  chatTitle: string;
  model: string;
  version: string;
  sessionId: string | null;
  messages: ChatMessage[];
  notes: Note[];
  chats: ChatThread[];
  activeFilter: TabFilter;
  isGrouped: boolean;
  activeTheme: GlassTheme;
  searchQuery: string;
  requestStatus: RequestStatus;
  backendStatus: BackendStatus;
  error: string | null;
}
