import { create } from 'zustand';
import type { WidgetDisplay, AudioDisplay, InputSchema } from '../api/types';

/* ------------------------------------------------------------------ */
/* Message & ToolStep value types                                     */
/* ------------------------------------------------------------------ */

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool' | 'error';
  content: string;
  rawContent?: string;
  steps?: ToolStep[];
  widgets?: WidgetDisplay[];
  audios?: AudioDisplay[];
  usage?: { input_tokens: number; output_tokens: number; total_tokens: number } | null;
  toolCallId?: string;
  timestamp: number;
}

export interface ToolStep {
  id: string;
  type: 'tool' | 'think';
  label: string;
  detail: string;
  renderedDetail: string;
  status: 'running' | 'done';
  isError: boolean;
  isSlow: boolean;
  startTime: number;
  toolCallId: string;
}

export interface HitlRequest {
  toolCallId: string;
  prompt: string;
  inputSchema: InputSchema;
}

/* ------------------------------------------------------------------ */
/* Store                                                              */
/* ------------------------------------------------------------------ */

interface ChatState {
  messages: ChatMessage[];
  streamingMessageId: string | null;
  isStreaming: boolean;
  pendingQueue: string[];
  currentText: string;
  thinkingText: string;
  steps: ToolStep[];
  stepsExpanded: boolean;
  usage: { input_tokens: number; output_tokens: number; total_tokens: number } | null;

  // Display blocks rendered during the current turn
  widgets: WidgetDisplay[];
  audios: AudioDisplay[];
  hitlRequest: HitlRequest | null;

  // actions
  addMessage: (msg: ChatMessage) => void;
  setStreamingMessageId: (id: string | null) => void;
  setStreaming: (v: boolean) => void;
  appendText: (text: string) => void;
  appendThinking: (text: string) => void;
  addStep: (step: ToolStep) => void;
  updateStep: (id: string, patch: Partial<ToolStep>) => void;
  findRunningStep: () => ToolStep | undefined;
  setUsage: (u: ChatState['usage']) => void;
  toggleSteps: () => void;
  enqueuePending: (text: string) => void;
  dequeuePending: () => string | undefined;
  addWidget: (w: WidgetDisplay) => void;
  addAudio: (a: AudioDisplay) => void;
  setHitlRequest: (h: HitlRequest | null) => void;
  resetSteps: () => void;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  streamingMessageId: null,
  isStreaming: false,
  pendingQueue: [],
  currentText: '',
  thinkingText: '',
  steps: [],
  stepsExpanded: false,
  usage: null,
  widgets: [],
  audios: [],
  hitlRequest: null,

  addMessage: (msg) =>
    set((s) => ({ messages: [...s.messages, msg] })),

  setStreamingMessageId: (id) => set({ streamingMessageId: id }),
  setStreaming: (v) => set({ isStreaming: v }),

  appendText: (text) =>
    set((s) => ({ currentText: s.currentText + text })),

  appendThinking: (text) =>
    set((s) => ({ thinkingText: s.thinkingText + text })),

  addStep: (step) =>
    set((s) => ({ steps: [...s.steps, step] })),

  updateStep: (id, patch) =>
    set((s) => ({
      steps: s.steps.map((st) => (st.id === id ? { ...st, ...patch } : st)),
    })),

  findRunningStep: () => get().steps.find((s) => s.status === 'running'),

  setUsage: (u) => set({ usage: u }),

  toggleSteps: () => set((s) => ({ stepsExpanded: !s.stepsExpanded })),

  enqueuePending: (text) =>
    set((s) => ({ pendingQueue: [...s.pendingQueue, text] })),

  dequeuePending: () => {
    const q = get().pendingQueue;
    if (q.length === 0) return undefined;
    const [head, ...rest] = q;
    set({ pendingQueue: rest });
    return head;
  },

  addWidget: (w) => set((s) => ({ widgets: [...s.widgets, w] })),
  addAudio: (a) => set((s) => ({ audios: [...s.audios, a] })),
  setHitlRequest: (h) => set({ hitlRequest: h }),

  resetSteps: () =>
    set({
      steps: [],
      currentText: '',
      thinkingText: '',
      usage: null,
      widgets: [],
      audios: [],
      hitlRequest: null,
    }),

  reset: () =>
    set({
      messages: [],
      streamingMessageId: null,
      isStreaming: false,
      pendingQueue: [],
      currentText: '',
      thinkingText: '',
      steps: [],
      usage: null,
      widgets: [],
      audios: [],
      hitlRequest: null,
    }),
}));
