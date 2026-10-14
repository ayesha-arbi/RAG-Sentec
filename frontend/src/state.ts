import { AppState, ChatMessage, Note, TabFilter, GlassTheme, Role } from './types.js';
import { initialAppState } from './data.js';

type StateListener = (state: AppState) => void;

class StateStore {
  private state: AppState;
  private listeners: Set<StateListener> = new Set();

  constructor() {
    this.state = { ...initialAppState };
  }

  public getState(): AppState {
    return this.state;
  }

  public subscribe(listener: StateListener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    for (const listener of this.listeners) {
      listener(this.state);
    }
  }

  public setFilter(filter: TabFilter): void {
    this.state = { ...this.state, activeFilter: filter };
    this.notify();
  }

  public toggleGrouped(): void {
    this.state = { ...this.state, isGrouped: !this.state.isGrouped };
    this.notify();
  }

  public setTheme(theme: GlassTheme): void {
    this.state = { ...this.state, activeTheme: theme };
    this.notify();
  }

  public setSearchQuery(query: string): void {
    this.state = { ...this.state, searchQuery: query };
    this.notify();
  }

  public addMessage(role: Role, text: string, label?: string, highlightedText?: string): ChatMessage {
    const newMessage: ChatMessage = {
      id: `msg-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
      role,
      text,
      label,
      highlightedText,
      timestamp: Date.now()
    };

    this.state = {
      ...this.state,
      messages: [...this.state.messages, newMessage]
    };
    this.notify();
    return newMessage;
  }

  public addNote(payload: Omit<Note, 'id' | 'createdAt'>): Note {
    const newNote: Note = {
      ...payload,
      id: `note-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
      createdAt: Date.now()
    };

    this.state = {
      ...this.state,
      notes: [newNote, ...this.state.notes]
    };
    this.notify();
    return newNote;
  }

  public deleteNote(id: string): void {
    this.state = {
      ...this.state,
      notes: this.state.notes.filter(n => n.id !== id)
    };
    this.notify();
  }

  public highlightToNote(text: string): Note {
    const trimmed = text.trim();
    const isUrl = /^https?:\/\/[^\s]+$/.test(trimmed) || trimmed.startsWith('twitter.com') || trimmed.startsWith('github.com');
    const isCode = trimmed.includes('{') || trimmed.includes('def ') || trimmed.includes('function ') || trimmed.includes('class ');

    const noteType = isUrl ? 'link' : isCode ? 'code' : 'text';

    return this.addNote({
      type: noteType,
      title: isCode ? 'CODE' : undefined,
      content: trimmed,
      url: isUrl ? (trimmed.startsWith('http') ? trimmed : `https://${trimmed}`) : undefined,
      highlighted: true
    });
  }

  public resetChat(newTitle: string = 'New Conversation'): void {
    this.state = {
      ...this.state,
      chatTitle: newTitle,
      messages: [
        {
          id: `msg-${Date.now()}`,
          role: 'context',
          text: 'Connected to intelligent cognitive engine. Ask questions, explore concepts, and capture ideas into notes.',
          timestamp: Date.now()
        }
      ]
    };
    this.notify();
  }
}

export const store = new StateStore();
