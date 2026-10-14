import { store } from './state.js';
import { UIManager } from './ui.js';
import { TabFilter, GlassTheme } from './types.js';

document.addEventListener('DOMContentLoaded', () => {
  const ui = new UIManager();

  // Subscribe UI to state updates
  store.subscribe(state => {
    ui.render(state);
  });

  // Handle composer form submission
  const composerForm = document.getElementById('composer') as HTMLFormElement | null;
  const inputEl = document.getElementById('input') as HTMLInputElement | null;
  const messagesEl = document.getElementById('messages') as HTMLElement | null;

  if (composerForm && inputEl) {
    composerForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const text = inputEl.value.trim();
      if (!text) return;

      // Add user message
      store.addMessage('user', text, 'You');
      inputEl.value = '';

      // Scroll messages down
      if (messagesEl) {
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }

      // Show typing indicator
      const typingEl = document.createElement('div');
      typingEl.className = 'msg assistant-msg typing-msg';
      typingEl.innerHTML = `
        <div class="label">Answer</div>
        <div class="typing-indicator">
          <span></span><span></span><span></span>
        </div>
      `;
      messagesEl?.appendChild(typingEl);
      if (messagesEl) {
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }

      // Simulate thoughtful AI reply
      setTimeout(() => {
        typingEl.remove();

        const cannedReplies = [
          {
            reply: 'Memory serves not just as an archive of the past, but as a generative substrate for future anticipation. In distributed cognitive architectures, synthetic memory structures can offload indexing while preserving subjective semantic coherence.',
            highlight: 'synthetic memory structures can offload indexing while preserving subjective semantic coherence'
          },
          {
            reply: 'Cognitive augmentation suggests that intelligence is relational. By establishing continuous bidirectional feedback loops with ambient neural notebooks, the perimeter of the human mind expands beyond biological bounds.',
            highlight: 'the perimeter of the human mind expands beyond biological bounds'
          },
          {
            reply: 'Neuroscience indicates that biological memory is reconstructive rather than photographic. When AI participates in this reconstruction, it transforms recollection from a static playback into an active co-creation.',
            highlight: 'transforms recollection from a static playback into an active co-creation'
          }
        ];

        const selectedReply = cannedReplies[Math.floor(Math.random() * cannedReplies.length)];
        store.addMessage('assistant', selectedReply.reply, 'Answer', selectedReply.highlight);

        if (messagesEl) {
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
      }, 850);
    });
  }

  // Handle Tabs click
  const tabsContainer = document.getElementById('tabs');
  if (tabsContainer) {
    tabsContainer.addEventListener('click', (e) => {
      const target = (e.target as HTMLElement).closest('.tab') as HTMLButtonElement | null;
      if (target && target.dataset.filter) {
        store.setFilter(target.dataset.filter as TabFilter);
      }
    });
  }

  // Handle Group Button
  const groupBtn = document.querySelector('.group-btn');
  if (groupBtn) {
    groupBtn.addEventListener('click', () => {
      store.toggleGrouped();
    });
  }

  // Handle Actions Button
  const actionsBtn = document.querySelector('.actions-btn');
  if (actionsBtn) {
    actionsBtn.addEventListener('click', () => {
      ui.showActionsModal();
    });
  }

  // Actions Modal buttons
  document.getElementById('modalAddNote')?.addEventListener('click', () => {
    document.getElementById('actionModal')?.classList.add('hidden');
    const noteText = prompt('Enter note text:');
    if (noteText && noteText.trim()) {
      store.addNote({
        type: 'text',
        content: noteText.trim(),
        highlighted: true
      });
    }
  });

  document.getElementById('modalAddLink')?.addEventListener('click', () => {
    document.getElementById('actionModal')?.classList.add('hidden');
    const url = prompt('Enter link URL (e.g. twitter.com/example):');
    if (url && url.trim()) {
      store.addNote({
        type: 'link',
        content: url.replace(/^https?:\/\//, ''),
        url: url.startsWith('http') ? url : `https://${url}`
      });
    }
  });

  document.getElementById('modalSummarize')?.addEventListener('click', () => {
    document.getElementById('actionModal')?.classList.add('hidden');
    store.addNote({
      type: 'text',
      content: 'AI serves as externalized memory: flips cognition from static storage to real-time semantic navigation.',
      highlighted: true
    });
  });

  // Theme pills in Actions modal
  document.querySelectorAll<HTMLButtonElement>('.theme-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.theme-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const theme = pill.dataset.theme as GlassTheme;
      if (theme) {
        store.setTheme(theme);
      }
    });
  });

  // Notes Grid card interactions (Open detail / links / media)
  const notesGrid = document.getElementById('notesGrid');
  if (notesGrid) {
    notesGrid.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      const noteEl = target.closest('.note') as HTMLElement | null;
      if (!noteEl) return;

      const noteId = noteEl.dataset.id;
      const note = store.getState().notes.find(n => n.id === noteId);
      if (!note) return;

      // If clicked Open button or dots or card itself (and not inside an <a> tag)
      if (target.closest('.open') || target.closest('.dots') || target.classList.contains('card') || target.closest('.card')) {
        if (!target.closest('a')) {
          ui.showNoteDetail(note);
        }
      }
    });
  }

  // Right Rail buttons
  document.getElementById('newChatBtn')?.addEventListener('click', () => {
    if (confirm('Start a new chat session?')) {
      store.resetChat();
    }
  });

  const railItems = document.querySelectorAll<HTMLButtonElement>('.right-rail .rail-item');
  if (railItems.length >= 4) {
    // All chats
    railItems[1].addEventListener('click', () => {
      ui.showChatsDrawer();
    });

    // Search
    railItems[2].addEventListener('click', () => {
      const query = prompt('Search notes & messages:');
      if (query !== null) {
        store.setSearchQuery(query);
      }
    });

    // Images
    railItems[3].addEventListener('click', () => {
      store.setFilter('media');
    });
  }

  // Chats drawer items click
  document.querySelectorAll<HTMLElement>('.chats-list .chat-item').forEach(item => {
    item.addEventListener('click', () => {
      const chatTitle = item.dataset.chat;
      if (chatTitle) {
        store.resetChat(chatTitle);
        document.getElementById('chatsDrawer')?.classList.add('hidden');
      }
    });
  });

  // Panel Resizer Slider between Chat and Notes
  initPanelResizer();

  // Model pill toggle (Prospecto Engine)
  const modelBtn = document.getElementById('modelBtn');
  if (modelBtn) {
    modelBtn.addEventListener('click', () => {
      const currentText = modelBtn.textContent || '';
      const isPro = currentText.includes('Pro');
      modelBtn.innerHTML = isPro
        ? `<svg class="prospecto-logo-icon" width="19" height="19" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2.5L20.5 7.5V16.5L12 21.5L3.5 16.5V7.5L12 2.5Z" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/>
            <path d="M12 2.5V21.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" opacity="0.85"/>
            <path d="M3.5 7.5L20.5 16.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" opacity="0.85"/>
            <path d="M3.5 16.5L20.5 7.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" opacity="0.85"/>
            <circle cx="12" cy="12" r="3.2" fill="#38bdf8" stroke="#ffffff" stroke-width="1.6"/>
          </svg> Prospecto`
        : `<svg class="prospecto-logo-icon pro" width="19" height="19" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2.5L20.5 7.5V16.5L12 21.5L3.5 16.5V7.5L12 2.5Z" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/>
            <path d="M12 2.5V21.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" opacity="0.85"/>
            <path d="M3.5 7.5L20.5 16.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" opacity="0.85"/>
            <path d="M3.5 16.5L20.5 7.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" opacity="0.85"/>
            <circle cx="12" cy="12" r="3.4" fill="#f59e0b" stroke="#ffffff" stroke-width="1.6"/>
          </svg> Prospecto Pro`;
    });
  }

  // Share button
  document.getElementById('shareBtn')?.addEventListener('click', () => {
    if (navigator.share) {
      navigator.share({
        title: store.getState().chatTitle,
        text: 'Prospecto - The Science and Philosophy of Consciousness workspace.'
      }).catch(() => {});
    } else {
      navigator.clipboard.writeText(window.location.href);
      alert('Prospecto link copied to clipboard!');
    }
  });
});

/**
 * Initializes the draggable resizer slider between Chat and Notes panels
 */
function initPanelResizer(): void {
  const resizer = document.getElementById('panelResizer');
  const shell = document.querySelector('.shell') as HTMLElement | null;
  if (!resizer || !shell) return;

  // Restore saved width from localStorage if exists
  const savedWidth = localStorage.getItem('prospecto_chat_width');
  if (savedWidth) {
    const parsed = parseInt(savedWidth, 10);
    if (!isNaN(parsed) && parsed >= 260 && parsed <= 900) {
      shell.style.setProperty('--chat-width', `${parsed}px`);
    }
  }

  let isDragging = false;
  let startX = 0;
  let startWidth = 0;

  const onPointerDown = (e: PointerEvent) => {
    isDragging = true;
    startX = e.clientX;
    const chatPanel = document.querySelector('.chat-panel') as HTMLElement | null;
    startWidth = chatPanel ? chatPanel.getBoundingClientRect().width : 360;

    resizer.classList.add('is-dragging');
    document.body.classList.add('resizing');
    resizer.setPointerCapture(e.pointerId);
    e.preventDefault();
  };

  const onPointerMove = (e: PointerEvent) => {
    if (!isDragging) return;
    const delta = e.clientX - startX;
    const minWidth = 260;
    const maxWidth = Math.max(340, window.innerWidth - 460);
    const newWidth = Math.min(Math.max(startWidth + delta, minWidth), maxWidth);

    shell.style.setProperty('--chat-width', `${Math.round(newWidth)}px`);
  };

  const onPointerUp = (e: PointerEvent) => {
    if (!isDragging) return;
    isDragging = false;
    resizer.classList.remove('is-dragging');
    document.body.classList.remove('resizing');
    try {
      resizer.releasePointerCapture(e.pointerId);
    } catch {}

    const chatPanel = document.querySelector('.chat-panel') as HTMLElement | null;
    if (chatPanel) {
      const finalWidth = Math.round(chatPanel.getBoundingClientRect().width);
      localStorage.setItem('prospecto_chat_width', finalWidth.toString());
    }
  };

  resizer.addEventListener('pointerdown', onPointerDown);
  resizer.addEventListener('pointermove', onPointerMove);
  resizer.addEventListener('pointerup', onPointerUp);
  resizer.addEventListener('pointercancel', onPointerUp);

  // Double-click to reset to default 360px
  resizer.addEventListener('dblclick', () => {
    shell.style.setProperty('--chat-width', '360px');
    localStorage.removeItem('prospecto_chat_width');
  });

  // Keyboard accessibility (ArrowLeft shrinks chat, ArrowRight expands chat)
  resizer.addEventListener('keydown', (e: KeyboardEvent) => {
    const chatPanel = document.querySelector('.chat-panel') as HTMLElement | null;
    const curWidth = chatPanel ? chatPanel.getBoundingClientRect().width : 360;
    if (e.key === 'ArrowLeft') {
      const newWidth = Math.max(260, curWidth - 24);
      shell.style.setProperty('--chat-width', `${newWidth}px`);
      localStorage.setItem('prospecto_chat_width', newWidth.toString());
      e.preventDefault();
    } else if (e.key === 'ArrowRight') {
      const maxWidth = Math.max(340, window.innerWidth - 460);
      const newWidth = Math.min(maxWidth, curWidth + 24);
      shell.style.setProperty('--chat-width', `${newWidth}px`);
      localStorage.setItem('prospecto_chat_width', newWidth.toString());
      e.preventDefault();
    }
  });
}
