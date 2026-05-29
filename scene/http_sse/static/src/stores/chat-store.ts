import { create } from 'zustand';
import type { WidgetDisplay, AudioDisplay, InputSchema } from '../api/types';
import { extractThinkSteps, getDisplayableText } from '../utils/think';

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
  loadMessages: (rawMessages: Array<{ role: string; content: unknown; timestamp?: number }>) => void;
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

  loadMessages: (rawMessages) => {
    const loaded: ChatMessage[] = [];
    let pendingSteps: ToolStep[] = [];

    const flushPending = (into: ChatMessage) => {
      if (pendingSteps.length > 0) {
        into.steps = [...pendingSteps, ...(into.steps || [])];
        pendingSteps = [];
      }
    };

    for (const msg of rawMessages) {
      const role = msg.role as 'user' | 'assistant' | 'tool';
      if (role !== 'user' && role !== 'assistant' && role !== 'tool') continue;

      if (role === 'assistant') {
        const parsed = parseAssistantMessage(msg.content);
        if (!parsed.text && parsed.steps.length === 0) continue;

        if (parsed.text) {
          // This message has visible text — create a card and merge pending steps
          const card: ChatMessage = {
            id: `loaded-${Date.now()}-${loaded.length}`,
            role,
            content: parsed.text,
            steps: parsed.steps.length > 0 ? parsed.steps : undefined,
            timestamp: msg.timestamp ? msg.timestamp * 1000 : Date.now(),
          };
          flushPending(card);
          loaded.push(card);
        } else {
          // No visible text, only steps — accumulate for next card with text
          pendingSteps.push(...parsed.steps);
        }
      } else {
        const content = extractTextContent(msg.content);
        if (!content) continue;
        const card: ChatMessage = {
          id: `loaded-${Date.now()}-${loaded.length}`,
          role,
          content,
          timestamp: msg.timestamp ? msg.timestamp * 1000 : Date.now(),
        };
        // If this is a user/tool message after pending steps, flush them into
        // the last assistant card if one exists, otherwise drop them
        if (pendingSteps.length > 0 && loaded.length > 0) {
          const last = loaded[loaded.length - 1];
          if (last.role === 'assistant') flushPending(last);
        }
        loaded.push(card);
      }
    }
    set({ messages: loaded });
  },
}));

function extractTextContent(raw: unknown): string {
  if (typeof raw === 'string') return raw;
  if (Array.isArray(raw)) {
    const parts: string[] = [];
    for (const item of raw) {
      if (typeof item === 'string') {
        parts.push(item);
      } else if (item && typeof item === 'object') {
        const type = (item as Record<string, unknown>).type;
        const text = (item as Record<string, unknown>).text;
        if (type === 'text' && typeof text === 'string') {
          parts.push(text);
        }
      }
    }
    return parts.join('');
  }
  return '';
}

function parseAssistantMessage(raw: unknown): { text: string; steps: ToolStep[] } {
  const steps: ToolStep[] = [];
  let fullText = '';

  if (Array.isArray(raw)) {
    for (const item of raw) {
      if (!item || typeof item !== 'object') continue;
      const type = (item as Record<string, unknown>).type;

      if (type === 'text') {
        const text = (item as Record<string, unknown>).text as string;
        if (text) fullText += text;
      } else if (type === 'tool_call') {
        const name = (item as Record<string, unknown>).name as string;
        const args = (item as Record<string, unknown>).arguments as Record<string, unknown>;
        const callId = (item as Record<string, unknown>).id as string;
        steps.push({
          id: `step-${callId || name}-${Date.now()}`,
          type: 'tool',
          label: name || 'tool',
          detail: JSON.stringify(args || {}),
          renderedDetail: '',
          status: 'done',
          isError: false,
          isSlow: false,
          startTime: Date.now(),
          toolCallId: callId || '',
        });
      }
    }
  } else if (typeof raw === 'string') {
    fullText = raw;
  }

  // Extract think blocks
  const seenThinks = new Set<string>();
  const thinkBlocks = extractThinkSteps(fullText, seenThinks);
  for (const block of thinkBlocks) {
    steps.push({
      id: `think-${block.content.slice(0, 16).replace(/\s+/g, '-')}-${Date.now()}`,
      type: 'think',
      label: '思考过程',
      detail: block.content,
      renderedDetail: '',
      status: 'done',
      isError: false,
      isSlow: false,
      startTime: Date.now(),
      toolCallId: '',
    });
  }

  return { text: getDisplayableText(fullText), steps };
}
