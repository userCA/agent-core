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
  loadSessionMessages: (sessionId: string) => Promise<void>;
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

  loadSessionMessages: async (sessionId) => {
    try {
      const resp = await fetch(`/session?session_id=${encodeURIComponent(sessionId)}`);
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.messages && data.messages.length > 0) {
        get().loadMessages(data.messages);
      }
    } catch { /* best-effort */ }
  },

  loadMessages: (rawMessages) => {
    const loaded: ChatMessage[] = [];
    let currentAssistant: ChatMessage | null = null;

    const flushAssistant = () => {
      if (currentAssistant) {
        if (
          currentAssistant.content ||
          (currentAssistant.steps && currentAssistant.steps.length > 0)
        ) {
          loaded.push(currentAssistant);
        }
        currentAssistant = null;
      }
    };

    for (const msg of rawMessages) {
      const role = msg.role as string;
      if (
        role !== 'user' &&
        role !== 'assistant' &&
        role !== 'tool' &&
        role !== 'tool_result'
      )
        continue;

      if (role === 'user') {
        flushAssistant();
        const content = extractTextContent(msg.content);
        if (!content) continue;
        loaded.push({
          id: `loaded-${Date.now()}-${loaded.length}`,
          role: 'user',
          content,
          timestamp: msg.timestamp ? msg.timestamp * 1000 : Date.now(),
        });
      } else if (role === 'assistant') {
        const parsed = parseAssistantMessage(msg.content);
        if (!parsed.text && parsed.steps.length === 0) continue;

        if (!currentAssistant) {
          currentAssistant = {
            id: `loaded-${Date.now()}-${loaded.length}`,
            role: 'assistant',
            content: parsed.text,
            steps: parsed.steps.length > 0 ? parsed.steps : undefined,
            timestamp: msg.timestamp ? msg.timestamp * 1000 : Date.now(),
          };
        } else {
          // Merge consecutive assistant messages into one card
          if (parsed.text) {
            currentAssistant.content = currentAssistant.content
              ? currentAssistant.content + '\n\n' + parsed.text
              : parsed.text;
          }
          if (parsed.steps.length > 0) {
            currentAssistant.steps = [
              ...(currentAssistant.steps || []),
              ...parsed.steps,
            ];
          }
        }
      } else {
        // tool or tool_result
        const content = extractTextContent(msg.content);
        if (!content) continue;

        const toolCallId =
          (msg as Record<string, unknown>).tool_call_id || '';
        const isError =
          (msg as Record<string, unknown>).is_error || false;

        // Try to match tool_result to an existing tool step in currentAssistant
        if (
          currentAssistant &&
          currentAssistant.steps &&
          role === 'tool_result'
        ) {
          const matchingStep = currentAssistant.steps.find(
            (s) => s.toolCallId === toolCallId
          );
          if (matchingStep) {
            matchingStep.detail = content;
            matchingStep.renderedDetail = content;
            matchingStep.isError = Boolean(isError);
            continue;
          }
        }

        // No match or legacy tool message — flush assistant and add as tool card
        flushAssistant();
        loaded.push({
          id: `loaded-${Date.now()}-${loaded.length}`,
          role: 'tool',
          content,
          toolCallId: String(toolCallId),
          timestamp: msg.timestamp ? msg.timestamp * 1000 : Date.now(),
        });
      }
    }

    flushAssistant();
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
