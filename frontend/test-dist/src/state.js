import { ApiClient, ApiError } from './api.js';
import { initialAppState } from './data.js';
function titleFromQuestion(question) {
    const trimmed = question.trim();
    return trimmed.length > 72 ? `${trimmed.slice(0, 72)}…` : trimmed;
}
function messageCount(messages) {
    return messages.filter(m => m.role !== 'context').length;
}
export class StateStore {
    constructor(client = new ApiClient()) {
        this.listeners = new Set();
        this.client = client;
        this.state = { ...initialAppState };
    }
    getState() {
        return this.state;
    }
    subscribe(listener) {
        this.listeners.add(listener);
        listener(this.state);
        return () => this.listeners.delete(listener);
    }
    notify() {
        for (const listener of this.listeners) {
            listener(this.state);
        }
    }
    currentChats(sessionId, chatTitle, messages) {
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
    composerLocked() {
        return (this.state.backendStatus !== 'ready' ||
            this.state.requestStatus === 'checking' ||
            this.state.requestStatus === 'loading');
    }
    async checkHealth() {
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
        }
        catch (err) {
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
    setFilter(filter) {
        this.state = { ...this.state, activeFilter: filter };
        this.notify();
    }
    toggleGrouped() {
        this.state = { ...this.state, isGrouped: !this.state.isGrouped };
        this.notify();
    }
    setTheme(theme) {
        this.state = { ...this.state, activeTheme: theme };
        this.notify();
    }
    setSearchQuery(query) {
        this.state = { ...this.state, searchQuery: query };
        this.notify();
    }
    async sendMessage(text) {
        const trimmed = text.trim();
        if (!trimmed || this.composerLocked()) {
            return;
        }
        const userMsg = {
            id: `msg-${Date.now()}-user`,
            role: 'user',
            text: trimmed,
            label: 'You',
            timestamp: Date.now()
        };
        const nextTitle = this.state.messages.length === 0 && this.state.chatTitle === 'Prospecto'
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
            const asstMsg = {
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
        }
        catch (err) {
            this.state = {
                ...this.state,
                requestStatus: 'idle',
                error: err instanceof Error ? err.message : 'Could not send the question.'
            };
        }
        this.notify();
    }
    addNote(payload) {
        const newNote = {
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
    deleteNote(id) {
        this.state = {
            ...this.state,
            notes: this.state.notes.filter(n => n.id !== id)
        };
        this.notify();
    }
    highlightToNote(text) {
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
    async resetChat() {
        const sessionId = this.state.sessionId;
        let cleanupError = null;
        if (sessionId) {
            try {
                await this.client.clearSession(sessionId);
            }
            catch (err) {
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
