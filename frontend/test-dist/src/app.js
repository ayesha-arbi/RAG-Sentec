import { store } from './state.js';
import { UIManager } from './ui.js';
document.addEventListener('DOMContentLoaded', () => {
    const ui = new UIManager();
    store.subscribe(state => {
        ui.render(state);
    });
    void store.checkHealth();
    const composerForm = document.getElementById('composer');
    const inputEl = document.getElementById('input');
    const messagesEl = document.getElementById('messages');
    if (composerForm && inputEl) {
        composerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (store.composerLocked())
                return;
            const text = inputEl.value.trim();
            if (!text)
                return;
            inputEl.value = '';
            await store.sendMessage(text);
            inputEl.focus();
            if (messagesEl) {
                messagesEl.scrollTop = messagesEl.scrollHeight;
            }
        });
    }
    document.getElementById('chatStatus')?.addEventListener('click', (e) => {
        const target = e.target;
        if (target.id === 'retryHealthBtn') {
            void store.checkHealth();
        }
    });
    const tabsContainer = document.getElementById('tabs');
    if (tabsContainer) {
        tabsContainer.addEventListener('click', (e) => {
            const target = e.target.closest('.tab');
            if (target && target.dataset.filter) {
                store.setFilter(target.dataset.filter);
            }
        });
    }
    const groupBtn = document.querySelector('.group-btn');
    if (groupBtn) {
        groupBtn.addEventListener('click', () => {
            store.toggleGrouped();
        });
    }
    const actionsBtn = document.querySelector('.actions-btn');
    if (actionsBtn) {
        actionsBtn.addEventListener('click', () => {
            ui.showActionsModal();
        });
    }
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
    document.querySelectorAll('.theme-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            document.querySelectorAll('.theme-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            const theme = pill.dataset.theme;
            if (theme) {
                store.setTheme(theme);
            }
        });
    });
    const notesGrid = document.getElementById('notesGrid');
    if (notesGrid) {
        notesGrid.addEventListener('click', (e) => {
            const target = e.target;
            const noteEl = target.closest('.note');
            if (!noteEl)
                return;
            const noteId = noteEl.dataset.id;
            const note = store.getState().notes.find(n => n.id === noteId);
            if (!note)
                return;
            if (target.closest('.open') || target.closest('.dots') || target.classList.contains('card') || target.closest('.card')) {
                if (!target.closest('a')) {
                    ui.showNoteDetail(note);
                }
            }
        });
    }
    document.getElementById('newChatBtn')?.addEventListener('click', () => {
        if (confirm('Start a new chat session?')) {
            void store.resetChat();
        }
    });
    const railItems = document.querySelectorAll('.right-rail .rail-item');
    if (railItems.length >= 4) {
        railItems[1].addEventListener('click', () => {
            ui.showChatsDrawer();
        });
        railItems[2].addEventListener('click', () => {
            const query = prompt('Search notes & messages:');
            if (query !== null) {
                store.setSearchQuery(query);
            }
        });
        railItems[3].addEventListener('click', () => {
            store.setFilter('media');
        });
    }
    document.getElementById('chatsDrawer')?.addEventListener('click', () => {
        document.getElementById('chatsDrawer')?.classList.add('hidden');
    });
    initPanelResizer();
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
    document.getElementById('shareBtn')?.addEventListener('click', () => {
        if (navigator.share) {
            navigator.share({
                title: store.getState().chatTitle,
                text: 'Prospecto — university prospectus RAG workspace.'
            }).catch(() => { });
        }
        else {
            navigator.clipboard.writeText(window.location.href);
            alert('Prospecto link copied to clipboard!');
        }
    });
});
function initPanelResizer() {
    const resizer = document.getElementById('panelResizer');
    const shell = document.querySelector('.shell');
    if (!resizer || !shell)
        return;
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
    const onPointerDown = (e) => {
        isDragging = true;
        startX = e.clientX;
        const chatPanel = document.querySelector('.chat-panel');
        startWidth = chatPanel ? chatPanel.getBoundingClientRect().width : 360;
        resizer.classList.add('is-dragging');
        document.body.classList.add('resizing');
        resizer.setPointerCapture(e.pointerId);
        e.preventDefault();
    };
    const onPointerMove = (e) => {
        if (!isDragging)
            return;
        const delta = e.clientX - startX;
        const minWidth = 260;
        const maxWidth = Math.max(340, window.innerWidth - 460);
        const newWidth = Math.min(Math.max(startWidth + delta, minWidth), maxWidth);
        shell.style.setProperty('--chat-width', `${Math.round(newWidth)}px`);
    };
    const onPointerUp = (e) => {
        if (!isDragging)
            return;
        isDragging = false;
        resizer.classList.remove('is-dragging');
        document.body.classList.remove('resizing');
        try {
            resizer.releasePointerCapture(e.pointerId);
        }
        catch { }
        const chatPanel = document.querySelector('.chat-panel');
        if (chatPanel) {
            const finalWidth = Math.round(chatPanel.getBoundingClientRect().width);
            localStorage.setItem('prospecto_chat_width', finalWidth.toString());
        }
    };
    resizer.addEventListener('pointerdown', onPointerDown);
    resizer.addEventListener('pointermove', onPointerMove);
    resizer.addEventListener('pointerup', onPointerUp);
    resizer.addEventListener('pointercancel', onPointerUp);
    resizer.addEventListener('dblclick', () => {
        shell.style.setProperty('--chat-width', '360px');
        localStorage.removeItem('prospecto_chat_width');
    });
    resizer.addEventListener('keydown', (e) => {
        const chatPanel = document.querySelector('.chat-panel');
        const curWidth = chatPanel ? chatPanel.getBoundingClientRect().width : 360;
        if (e.key === 'ArrowLeft') {
            const newWidth = Math.max(260, curWidth - 24);
            shell.style.setProperty('--chat-width', `${newWidth}px`);
            localStorage.setItem('prospecto_chat_width', newWidth.toString());
            e.preventDefault();
        }
        else if (e.key === 'ArrowRight') {
            const maxWidth = Math.max(340, window.innerWidth - 460);
            const newWidth = Math.min(maxWidth, curWidth + 24);
            shell.style.setProperty('--chat-width', `${newWidth}px`);
            localStorage.setItem('prospecto_chat_width', newWidth.toString());
            e.preventDefault();
        }
    });
}
