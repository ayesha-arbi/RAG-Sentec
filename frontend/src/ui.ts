import { AppState, ChatMessage, Note, TabFilter } from './types.js';
import { store } from './state.js';

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export class UIManager {
  private messagesContainer: HTMLElement;
  private notesGrid: HTMLElement;
  private tabsContainer: HTMLElement;
  private chatTitleEl: HTMLElement;
  private groupBtn: HTMLElement;
  private quickHighlightTooltip: HTMLElement;

  constructor() {
    this.messagesContainer = document.getElementById('messages') as HTMLElement;
    this.notesGrid = document.getElementById('notesGrid') as HTMLElement;
    this.tabsContainer = document.getElementById('tabs') as HTMLElement;
    this.chatTitleEl = document.getElementById('chatTitle') as HTMLElement;
    this.groupBtn = document.querySelector('.group-btn') as HTMLElement;

    this.quickHighlightTooltip = this.createTooltipElement();
    this.setupGlobalModals();
    this.setupTextSelection();
  }

  private createTooltipElement(): HTMLElement {
    const tooltip = document.createElement('div');
    tooltip.className = 'highlight-tooltip hidden';
    tooltip.innerHTML = `
      <button class="tooltip-btn" id="saveHighlightBtn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
        <span>Add to Notes</span>
      </button>
    `;
    document.body.appendChild(tooltip);
    return tooltip;
  }

  private setupGlobalModals(): void {
    if (!document.getElementById('actionModal')) {
      const modal = document.createElement('div');
      modal.id = 'actionModal';
      modal.className = 'modal-backdrop hidden';
      modal.innerHTML = `
        <div class="glass-modal">
          <div class="modal-header">
            <h3>Actions & Ambiance</h3>
            <button class="close-modal-btn" data-close="actionModal">&times;</button>
          </div>
          <div class="modal-actions-list">
            <button class="modal-action-row" id="modalAddNote">
              <span class="action-icon">📝</span>
              <div class="action-text">
                <strong>Create New Note</strong>
                <small>Write a custom text, idea, or finding</small>
              </div>
            </button>
            <button class="modal-action-row" id="modalAddLink">
              <span class="action-icon">🔗</span>
              <div class="action-text">
                <strong>Add Link Reference</strong>
                <small>Bookmark a link or article</small>
              </div>
            </button>
            <button class="modal-action-row" id="modalSummarize">
              <span class="action-icon">✨</span>
              <div class="action-text">
                <strong>Summarize Key Insight</strong>
                <small>Extract essence into an instant note card</small>
              </div>
            </button>
            <div class="modal-divider"></div>
            <div class="theme-picker-section">
              <label>Glass Surface Aesthetic:</label>
              <div class="theme-pill-group">
                <button class="theme-pill active" data-theme="frosted-glass">Frosted Glass</button>
                <button class="theme-pill" data-theme="crystal-clean">Crystal Clean</button>
                <button class="theme-pill" data-theme="slate-glass">Slate Frost</button>
                <button class="theme-pill" data-theme="dark-frosted">Dark Frosted</button>
              </div>
            </div>
          </div>
        </div>
      `;
      document.body.appendChild(modal);

      modal.addEventListener('click', (e) => {
        if (e.target === modal || (e.target as HTMLElement).dataset.close === 'actionModal') {
          modal.classList.add('hidden');
        }
      });
    }

    if (!document.getElementById('noteDetailModal')) {
      const detailModal = document.createElement('div');
      detailModal.id = 'noteDetailModal';
      detailModal.className = 'modal-backdrop hidden';
      detailModal.innerHTML = `
        <div class="glass-modal detail-modal">
          <div class="modal-header">
            <h3 id="detailNoteTitle">Note Details</h3>
            <button class="close-modal-btn" data-close="noteDetailModal">&times;</button>
          </div>
          <div class="detail-body" id="detailNoteBody"></div>
          <div class="modal-footer">
            <button class="pill pill-outline" id="copyNoteBtn">Copy Content</button>
            <button class="pill pill-danger" id="deleteNoteBtn">Delete Note</button>
          </div>
        </div>
      `;
      document.body.appendChild(detailModal);

      detailModal.addEventListener('click', (e) => {
        if (e.target === detailModal || (e.target as HTMLElement).dataset.close === 'noteDetailModal') {
          detailModal.classList.add('hidden');
        }
      });
    }

    if (!document.getElementById('chatsDrawer')) {
      const drawer = document.createElement('div');
      drawer.id = 'chatsDrawer';
      drawer.className = 'drawer-backdrop hidden';
      drawer.innerHTML = `
        <div class="glass-drawer">
          <div class="drawer-header">
            <h3>All Chats</h3>
            <button class="close-modal-btn" data-close="chatsDrawer">&times;</button>
          </div>
          <div class="chats-list">
            <div class="chat-item active" data-chat="The Science and Philosophy of Consciousness">
              <div class="chat-item-title">The Science and Philosophy of Consciousness</div>
              <div class="chat-item-meta">Active • 3 messages • Prospecto 6.0</div>
            </div>
            <div class="chat-item" data-chat="Neural Architectures & Cognitive Retrievability">
              <div class="chat-item-title">Neural Architectures & Cognitive Retrievability</div>
              <div class="chat-item-meta">Yesterday • 14 notes saved</div>
            </div>
            <div class="chat-item" data-chat="Epistemology of Synthetic Memory">
              <div class="chat-item-title">Epistemology of Synthetic Memory</div>
              <div class="chat-item-meta">3 days ago • 8 notes saved</div>
            </div>
          </div>
        </div>
      `;
      document.body.appendChild(drawer);

      drawer.addEventListener('click', (e) => {
        if (e.target === drawer || (e.target as HTMLElement).dataset.close === 'chatsDrawer') {
          drawer.classList.add('hidden');
        }
      });
    }
  }

  private setupTextSelection(): void {
    let selectedText = '';

    document.addEventListener('mouseup', () => {
      const selection = window.getSelection();
      const text = selection ? selection.toString().trim() : '';

      if (text.length > 5 && this.messagesContainer.contains(selection?.anchorNode || null)) {
        selectedText = text;
        const range = selection?.getRangeAt(0);
        if (range) {
          const rect = range.getBoundingClientRect();
          this.quickHighlightTooltip.style.top = `${rect.top + window.scrollY - 38}px`;
          this.quickHighlightTooltip.style.left = `${rect.left + window.scrollX + rect.width / 2 - 50}px`;
          this.quickHighlightTooltip.classList.remove('hidden');
        }
      } else {
        setTimeout(() => {
          if (!this.quickHighlightTooltip.matches(':hover')) {
            this.quickHighlightTooltip.classList.add('hidden');
          }
        }, 150);
      }
    });

    const saveHighlightBtn = document.getElementById('saveHighlightBtn');
    if (saveHighlightBtn) {
      saveHighlightBtn.addEventListener('click', () => {
        if (selectedText) {
          store.highlightToNote(selectedText);
          this.quickHighlightTooltip.classList.add('hidden');
          window.getSelection()?.removeAllRanges();
        }
      });
    }
  }

  public render(state: AppState): void {
    // 1. Update theme attribute
    document.body.dataset.theme = state.activeTheme;

    // 2. Update Chat Title
    if (this.chatTitleEl && this.chatTitleEl.textContent !== state.chatTitle) {
      this.chatTitleEl.textContent = state.chatTitle;
    }

    // 3. Render Messages
    this.renderMessages(state.messages);

    // 4. Render Tabs
    this.renderTabs(state.activeFilter);

    // 5. Render Notes
    this.renderNotes(state.notes, state.activeFilter, state.isGrouped, state.searchQuery);

    // 6. Update Group Button State
    if (this.groupBtn) {
      this.groupBtn.classList.toggle('active-pill', state.isGrouped);
    }
  }

  private renderMessages(messages: ChatMessage[]): void {
    if (!this.messagesContainer) return;

    this.messagesContainer.innerHTML = messages.map(msg => {
      if (msg.role === 'context') {
        return `
          <div class="msg context-msg">
            <div class="text faded-text">${escapeHtml(msg.text)}</div>
          </div>
        `;
      }

      let renderedText = escapeHtml(msg.text);

      if (msg.highlightedText) {
        const escapedHighlight = escapeHtml(msg.highlightedText);
        renderedText = renderedText.replace(
          escapedHighlight,
          `<mark class="highlight-bubble" data-highlight="${encodeURIComponent(msg.highlightedText)}" title="Saved highlight">${escapedHighlight}</mark>`
        );
      }

      const roleClass = msg.role === 'user' ? 'user-msg' : 'assistant-msg';
      const labelHtml = msg.label ? `<div class="label">${escapeHtml(msg.label)}</div>` : '';

      return `
        <div class="msg ${roleClass}" data-id="${msg.id}">
          ${labelHtml}
          <div class="text">${renderedText}</div>
        </div>
      `;
    }).join('');
  }

  private renderTabs(activeFilter: TabFilter): void {
    if (!this.tabsContainer) return;

    const tabs = this.tabsContainer.querySelectorAll<HTMLButtonElement>('.tab');
    tabs.forEach(tab => {
      const filter = tab.dataset.filter as TabFilter;
      if (filter === activeFilter) {
        tab.classList.add('active');
      } else {
        tab.classList.remove('active');
      }
    });
  }

  private renderNotes(notes: Note[], filter: TabFilter, isGrouped: boolean, searchQuery: string): void {
    if (!this.notesGrid) return;

    // Filter by tab
    let filtered = notes.filter(note => {
      if (filter === 'highlight') {
        return note.highlighted || note.type === 'text';
      }
      if (filter === 'link') {
        return note.type === 'link';
      }
      if (filter === 'media') {
        return note.type === 'media';
      }
      return true;
    });

    // Filter by search query if any
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(n =>
        n.content.toLowerCase().includes(q) ||
        (n.title && n.title.toLowerCase().includes(q)) ||
        (n.url && n.url.toLowerCase().includes(q))
      );
    }

    this.notesGrid.className = `notes-grid ${isGrouped ? 'grouped-mode' : 'masonry-mode'}`;

    if (filtered.length === 0) {
      this.notesGrid.innerHTML = `
        <div class="empty-notes">
          <p>No notes found in "${filter}"</p>
          <small>Highlight text from the conversation or click Actions to add one.</small>
        </div>
      `;
      return;
    }

    this.notesGrid.innerHTML = filtered.map(note => {
      switch (note.type) {
        case 'text':
          return `
            <article class="note text-note" data-id="${note.id}">
              <div class="card">
                <span class="dots" title="Note options">•••</span>
                <p class="card-content">${escapeHtml(note.content)}</p>
              </div>
              <button class="open" data-action="open" data-id="${note.id}">Open</button>
            </article>
          `;

        case 'link':
          return `
            <article class="note link-note" data-id="${note.id}">
              <span class="dots" title="Note options">•••</span>
              <a href="${note.url || '#'}" target="_blank" rel="noopener noreferrer">${escapeHtml(note.content)}</a>
            </article>
          `;

        case 'code':
          return `
            <article class="note code-note" data-id="${note.id}">
              <span class="dots" title="Note options">•••</span>
              <div class="code-label">${escapeHtml(note.title || 'CODE')}</div>
              <pre><code>${escapeHtml(note.content)}</code></pre>
            </article>
          `;

        case 'media':
          return `
            <article class="note media-note" data-id="${note.id}">
              <span class="dots" title="Note options">•••</span>
              <img src="${note.imageUrl}" alt="${escapeHtml(note.title || 'Note media')}" onerror="this.onerror=null;this.src='https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=700&q=80';" />
              <div class="media-icon" title="Media asset">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="3" ry="3"/>
                  <circle cx="8.5" cy="8.5" r="1.5"/>
                  <polyline points="21 15 16 10 5 21"/>
                </svg>
              </div>
            </article>
          `;

        default:
          return '';
      }
    }).join('');
  }

  public showNoteDetail(note: Note): void {
    const modal = document.getElementById('noteDetailModal');
    const titleEl = document.getElementById('detailNoteNoteTitle') || document.getElementById('detailNoteTitle');
    const bodyEl = document.getElementById('detailNoteBody');
    const copyBtn = document.getElementById('copyNoteBtn');
    const deleteBtn = document.getElementById('deleteNoteBtn');

    if (!modal || !bodyEl) return;

    if (titleEl) {
      titleEl.textContent = note.title || (note.type === 'link' ? 'Web Link' : note.type === 'code' ? 'Code Snippet' : 'Note');
    }

    if (note.type === 'code') {
      bodyEl.innerHTML = `<pre class="detail-code"><code>${escapeHtml(note.content)}</code></pre>`;
    } else if (note.type === 'media') {
      bodyEl.innerHTML = `
        <div class="detail-media">
          <img src="${note.imageUrl}" alt="Media note" />
          <p>${escapeHtml(note.content)}</p>
        </div>
      `;
    } else if (note.type === 'link') {
      bodyEl.innerHTML = `
        <p class="detail-link"><a href="${note.url || '#'}" target="_blank">${escapeHtml(note.content)}</a></p>
      `;
    } else {
      bodyEl.innerHTML = `<p class="detail-text">${escapeHtml(note.content)}</p>`;
    }

    if (copyBtn) {
      copyBtn.onclick = () => {
        navigator.clipboard.writeText(note.content);
        copyBtn.textContent = 'Copied!';
        setTimeout(() => copyBtn.textContent = 'Copy Content', 1500);
      };
    }

    if (deleteBtn) {
      deleteBtn.onclick = () => {
        store.deleteNote(note.id);
        modal.classList.add('hidden');
      };
    }

    modal.classList.remove('hidden');
  }

  public showActionsModal(): void {
    const modal = document.getElementById('actionModal');
    if (modal) {
      modal.classList.remove('hidden');
    }
  }

  public showChatsDrawer(): void {
    const drawer = document.getElementById('chatsDrawer');
    if (drawer) {
      drawer.classList.remove('hidden');
    }
  }
}
