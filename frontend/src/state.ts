import { ApiClient, ApiError } from './api.js';
import { initialAppState } from './data.js';
import { AppState, ChatMessage, ChatThread, GlassTheme, Note, TabFilter } from './types.js';

type StateListener = (state: AppState) => void;

function titleFromQuestion(question: string): string {
  const trimmed = question.trim();
  return trimmed.length > 72 ? `${trimmed.slice(0, 72)}…` : trimmed;
}

function messageCount(messages: ChatMessage[]): number {
  return messages.filter(m => m.role !== 'context').length;
}

export class StateStore {
  private state: AppState;
  private listeners: Set<StateListener> = new Set();
  private readonly client: ApiClient;

  constructor(client: ApiClient = new ApiClient()) {
    this.client = client;
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

  private currentChats(sessionId: string | null, chatTitle: string, messages: ChatMessage[]): ChatThread[] {
    const count = messageCount(messages);
    if (!sessionId && count === 0) {
      return [];
    }
    return [
      {
        id: sessionId || 'current',
        title: chatTitle,
        meta: count === 0 ? 'Current session' : `${count} messages`,
        messageCount: count,
        updatedAt: Date.now()
      }
    ];
  }

  public composerLocked(): boolean {
    return (
      this.state.backendStatus !== 'ready' ||
      this.state.requestStatus === 'checking' ||
      this.state.requestStatus === 'loading'
    );
  }

  public async checkHealth(): Promise<void> {
    this.state = {
      ...this.state,
      requestStatus: 'checking',
      error: null
    };
    this.notify();

    try {
      await this.client.health();
      this.state = {
        ...this.state,
        requestStatus: 'idle',
        backendStatus: 'ready',
        error: null
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not reach the Prospecto API.';
      const status = err instanceof ApiError ? err.status : undefined;
      this.state = {
        ...this.state,
        requestStatus: 'idle',
        backendStatus: status === 503 ? 'index_not_ready' : 'unavailable',
        error: message
      };
    }
    this.notify();
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

  public async sendMessage(text: string): Promise<void> {
    const trimmed = text.trim();
    if (!trimmed || this.composerLocked()) {
      return;
    }

    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}-user`,
      role: 'user',
      text: trimmed,
      label: 'You',
      timestamp: Date.now()
    };

    const nextTitle =
      this.state.messages.length === 0 && this.state.chatTitle === 'Prospecto'
        ? titleFromQuestion(trimmed)
        : this.state.chatTitle;
    const messages = [...this.state.messages, userMsg];

    this.state = {
      ...this.state,
      chatTitle: nextTitle,
      messages,
      chats: this.currentChats(this.state.sessionId, nextTitle, messages),
      requestStatus: 'loading',
      error: null
    };
    this.notify();

    try {
      const res = await this.client.chat(trimmed, this.state.sessionId, false, 8);
      const asstMsg: ChatMessage = {
        id: `msg-${Date.now()}-asst`,
        role: 'assistant',
        text: res.answer,
        label: 'Answer',
        timestamp: Date.now(),
        sources: res.sources,
        standaloneQuestion: res.standalone_question
      };
      const nextMessages = [...this.state.messages, asstMsg];
      this.state = {
        ...this.state,
        sessionId: res.session_id,
        messages: nextMessages,
        chats: this.currentChats(res.session_id, this.state.chatTitle, nextMessages),
        requestStatus: 'idle',
        error: null
      };
    } catch (err) {
      this.state = {
        ...this.state,
        requestStatus: 'idle',
        error: err instanceof Error ? err.message : 'Could not send the question.'
      };
    }
    this.notify();
  }

  public addNote(payload: Omit<Note, 'id' | 'createdAt'>): Note {
    const newNote: Note = {
      ...payload,
      id: `note-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
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

  public async resetChat(): Promise<void> {
    const sessionId = this.state.sessionId;
    let cleanupError: string | null = null;

    if (sessionId) {
      try {
        await this.client.clearSession(sessionId);
      } catch (err) {
        cleanupError = err instanceof Error ? err.message : 'Could not clear the server session.';
      }
    }

    this.state = {
      ...this.state,
      chatTitle: 'Prospecto',
      sessionId: null,
      messages: [],
      chats: [],
      requestStatus: 'idle',
      error: cleanupError ? `Started a new chat, but the previous session could not be cleared: ${cleanupError}` : null
    };
    this.notify();
  }
}

export const store = new StateStore();
