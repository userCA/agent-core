import { create } from 'zustand';
import type { WidgetDisplay, AudioDisplay, InputSchema } from '../api/types';
import { extractThinkSteps, getDisplayableText } from '../utils/think';

/* ------------------------------------------------------------------ */
/* Message & ToolStep value types                                     */
/* ------------------------------------------------------------------ */

export interface DelegationAgentItem {
  agent: string;
  status: 'running' | 'completed' | 'failed' | 'aborted';
  task?: string;
  summary?: string;
}

export interface PlanStepItem {
  id: string;
  title: string;
  status: string;
  detail?: string | null;
}

export interface MessageBlock {
  type: 'text' | 'think' | 'tool' | 'widget' | 'video' | 'delegation' | 'plan' | 'workflow';
  text?: string;
  label?: string;
  detail?: string;
  isError?: boolean;
  status?: 'running' | 'done';
  widget?: WidgetDisplay;
  videoUrl?: string;
  videoSize?: string;
  videoSeconds?: string;
  mode?: string;
  agents?: DelegationAgentItem[];
  planId?: string;
  planTitle?: string;
  planStatus?: string;
  planDone?: number;
  planTotal?: number;
  planSteps?: PlanStepItem[];
  workflowRunId?: string;
  workflowName?: string;
  workflowStatus?: string;
  workflowPhase?: string | null;
  workflowPhases?: string[];
  workflowLog?: string[];
  workflowCompletedAgents?: number;
  workflowTotalAgents?: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool' | 'error';
  content: string;
  blocks?: MessageBlock[];
  widgets?: WidgetDisplay[];
  audios?: AudioDisplay[];
  usage?: { input_tokens: number; output_tokens: number; total_tokens: number } | null;
  toolCallId?: string;
  timestamp: number;
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
  streamBlocks: MessageBlock[];
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
  setUsage: (u: ChatState['usage']) => void;
  enqueuePending: (text: string) => void;
  dequeuePending: () => string | undefined;
  removePending: (index: number) => void;
  addWidget: (w: WidgetDisplay) => void;
  addAudio: (a: AudioDisplay) => void;
  setHitlRequest: (h: HitlRequest | null) => void;
  setStreamBlocks: (blocks: MessageBlock[]) => void;
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
  streamBlocks: [],
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

  setUsage: (u) => set({ usage: u }),

  enqueuePending: (text) =>
    set((s) => ({ pendingQueue: [...s.pendingQueue, text] })),

  dequeuePending: () => {
    const q = get().pendingQueue;
    if (q.length === 0) return undefined;
    const [head, ...rest] = q;
    set({ pendingQueue: rest });
    return head;
  },

  removePending: (index) =>
    set((s) => ({
      pendingQueue: s.pendingQueue.filter((_, i) => i !== index),
    })),

  addWidget: (w) => set((s) => ({ widgets: [...s.widgets, w] })),
  addAudio: (a) => set((s) => ({ audios: [...s.audios, a] })),
  setHitlRequest: (h) => set({ hitlRequest: h }),

  setStreamBlocks: (blocks) => set({ streamBlocks: blocks }),
  resetSteps: () =>
    set({
      streamBlocks: [],
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
          (currentAssistant.blocks && currentAssistant.blocks.length > 0)
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
        if (parsed.blocks.length === 0) continue;

        if (!currentAssistant) {
          currentAssistant = {
            id: `loaded-${Date.now()}-${loaded.length}`,
            role: 'assistant',
            content: extractTextContent(msg.content) || '',
            blocks: parsed.blocks,
            timestamp: msg.timestamp ? msg.timestamp * 1000 : Date.now(),
          };
        } else {
          currentAssistant.blocks = [
            ...(currentAssistant.blocks || []),
            ...parsed.blocks,
          ];
          currentAssistant.content = extractTextContent([
            ...((currentAssistant as any)._rawContent || []),
            ...(Array.isArray(msg.content) ? msg.content : []),
          ]) || currentAssistant.content;
        }
      } else if (role === 'tool_result') {
        const content = extractTextContent(msg.content);
        if (currentAssistant?.blocks) {
          const toolName = (msg as Record<string, unknown>).tool_name as string;
          // Find matching tool block (reverse order, by tool name match)
          let toolBlk: MessageBlock | undefined;
          for (let i = currentAssistant.blocks.length - 1; i >= 0; i--) {
            const b = currentAssistant.blocks[i];
            if (b.type === 'tool' && b.label === toolName) {
              toolBlk = b;
              break;
            }
          }
          if (toolBlk) {
            // If show_widget, reconstruct widget block from persisted tool_call args
            if (toolName === 'show_widget' && toolBlk.detail) {
              try {
                const args = JSON.parse(toolBlk.detail);
                if (args.html) {
                  currentAssistant.blocks.push({
                    type: 'widget',
                    widget: {
                      version: 1,
                      html: args.html as string,
                      title: args.title as string | undefined,
                      height: Math.min(Number(args.height) || 400, 1200),
                    },
                  });
                }
              } catch { /* args JSON parse failed, skip widget */ }
            }
            // If generate_video or check_video_status, reconstruct video block from persisted result
            if ((toolName === 'generate_video' || toolName === 'check_video_status' || toolName === 'create_short_drama' || toolName === 'concat_videos') && content) {
              const videoMatch = content.match(/https?:\/\/\S+\.mp4\b/) ||
                content.match(/(\/renders\/\S+\.mp4)/);
              if (videoMatch) {
                const sizeMatch = content.match(/分辨率\**:\s*(\S+)/);
                const secMatch = content.match(/时长\**:\s*([\d.]+)s/);
                currentAssistant.blocks.push({
                  type: 'video',
                  videoUrl: videoMatch[0],
                  videoSize: sizeMatch?.[1],
                  videoSeconds: secMatch?.[1],
                });
              }
            }
            // Replace args with result content
            if (content) {
              toolBlk.detail = content;
              toolBlk.isError = Boolean((msg as Record<string, unknown>).is_error);
            }
          }
          // Reconstruct workflow block from run_workflow tool result (no matching tool block)
          if (toolName === 'run_workflow' && content) {
            const statusMatch = content.match(/status=(\w+)/);
            const phaseMatch = content.match(/phase=(\w+)/);
            const nameMatch = content.match(/\[workflow:([^\]]+)\]/);
            // Parse JSON body for phases (items) and log (analyses)
            let phases: string[] | undefined;
            let logEntries: string[] | undefined;
            const jsonMatch = content.match(/\n(\{[\s\S]*\})\s*$/);
            if (jsonMatch) {
              try {
                const data = JSON.parse(jsonMatch[1]);
                if (Array.isArray(data.items)) phases = data.items.map(String);
                if (data.analyses && typeof data.analyses === 'object') {
                  logEntries = Object.entries(data.analyses).map(
                    ([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`
                  );
                }
              } catch { /* JSON parse failed, skip phases/log */ }
            }
            currentAssistant.blocks.push({
              type: 'workflow',
              label: nameMatch?.[1] || '工作流',
              workflowName: nameMatch?.[1],
              workflowStatus: statusMatch?.[1] || 'completed',
              workflowPhase: phaseMatch?.[1] || null,
              workflowPhases: phases,
              workflowLog: logEntries,
              status: 'done',
              isError: statusMatch?.[1] === 'failed' || statusMatch?.[1] === 'aborted',
            });
          }
        }
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

function parseAssistantMessage(raw: unknown): { blocks: MessageBlock[] } {
  const blocks: MessageBlock[] = [];

  if (Array.isArray(raw)) {
    for (const item of raw) {
      if (!item || typeof item !== 'object') continue;
      const type = (item as Record<string, unknown>).type;

      if (type === 'text') {
        const text = (item as Record<string, unknown>).text as string;
        if (text) blocks.push({ type: 'text', text });
      } else if (type === 'tool_call') {
        const name = (item as Record<string, unknown>).name as string || 'tool';
        // Skip run_workflow — reconstructed as workflow block from tool_result
        if (name === 'run_workflow') continue;
        const args = (item as Record<string, unknown>).arguments as Record<string, unknown>;
        blocks.push({ type: 'tool', label: name, detail: JSON.stringify(args || {}) });
      }
    }
  } else if (typeof raw === 'string') {
    if (raw.trim()) blocks.push({ type: 'text', text: raw });
  }

  return { blocks };
}
