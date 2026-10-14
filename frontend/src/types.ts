export type Role = 'user' | 'assistant' | 'context';

export type NoteType = 'text' | 'link' | 'code' | 'media';

export type TabFilter = 'all' | 'highlight' | 'link' | 'media';

export type GlassTheme = 'frosted-glass' | 'crystal-clean' | 'slate-glass' | 'dark-frosted';

export interface ChatMessage {
  id: string;
  role: Role;
  text: string;
  label?: string;
  highlightedText?: string;
  timestamp: number;
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

export interface AppState {
  chatTitle: string;
  model: string;
  version: string;
  messages: ChatMessage[];
  notes: Note[];
  activeFilter: TabFilter;
  isGrouped: boolean;
  activeTheme: GlassTheme;
  searchQuery: string;
}
