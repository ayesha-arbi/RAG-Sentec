import { AppState } from './types.js';

export const initialAppState: AppState = {
  chatTitle: 'Prospecto',
  model: 'Prospecto',
  version: '6.0',
  sessionId: null,
  messages: [],
  notes: [],
  chats: [],
  activeFilter: 'all',
  isGrouped: false,
  activeTheme: 'frosted-glass',
  searchQuery: '',
  requestStatus: 'checking',
  backendStatus: 'unknown',
  error: null
};
