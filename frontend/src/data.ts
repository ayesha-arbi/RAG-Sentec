import { ChatMessage, Note, AppState } from './types.js';

export const initialMessages: ChatMessage[] = [
  {
    id: 'msg-0',
    role: 'context',
    text: 'images, conversations—and allow instant retrieval. "Instead of remembering facts, humans might remember how to ask." This flips the role of memory from storage to navigation.',
    timestamp: Date.now() - 3600000
  },
  {
    id: 'msg-1',
    role: 'user',
    label: 'You',
    text: 'Can AI extend or replace human memory?',
    timestamp: Date.now() - 1800000
  },
  {
    id: 'msg-2',
    role: 'assistant',
    label: 'Answer',
    text: 'Some researchers see AI as an externalized memory system. "AI may become the notebook of the mind, storing everything we might otherwise forget." But there are risks: over-reliance on AI can weaken natural recall and change how we value memory itself.',
    highlightedText: 'AI may become the notebook of the mind, storing everything we might otherwise forget.',
    timestamp: Date.now() - 900000
  }
];

export const initialNotes: Note[] = [
  {
    id: 'note-1',
    type: 'text',
    content: 'Could memory augmentation change identity',
    highlighted: true,
    createdAt: Date.now() - 3000000
  },
  {
    id: 'note-5',
    type: 'media',
    title: 'Architectural metaphor',
    content: 'Sunlit interior room with moss-covered grass ground, table, and warm orange booth seating.',
    imageUrl: 'assets/grass_room.svg',
    createdAt: Date.now() - 2800000
  },
  {
    id: 'note-2',
    type: 'link',
    content: 'twitter.com/eugene_mindset',
    url: 'https://twitter.com/eugene_mindset',
    createdAt: Date.now() - 2500000
  },
  {
    id: 'note-3',
    type: 'text',
    content: 'Metaphors and visual images that help explain consciousness',
    createdAt: Date.now() - 2000000
  },
  {
    id: 'note-4',
    type: 'code',
    title: 'CODE',
    content: `CLASS AIMEMORY:\n  DEF\n__INIT__(SELF):\n    SELF.STORAGE\n= {}\n\n  DEF\nREMEMBER(SELF, KEY,\nVALUE):\n  SELF.STORAGE[KEY] = ...`,
    isCode: true,
    createdAt: Date.now() - 1500000
  }
];

export const initialAppState: AppState = {
  chatTitle: 'The Science and Philosophy of Consciousness',
  model: 'Prospecto',
  version: '6.0',
  messages: initialMessages,
  notes: initialNotes,
  activeFilter: 'all',
  isGrouped: false,
  activeTheme: 'frosted-glass',
  searchQuery: ''
};
