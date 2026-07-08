import { useRef, useCallback } from 'react';
import { streamChat, abortSession } from '../api/client';
import { useChatStore, type HitlRequest, type MessageBlock } from '../stores/chat-store';
import { useSessionStore } from '../stores/session-store';
import { useUIStore } from '../stores/ui-store';
import { useToastStore } from '../stores/toast-store';
import { useModelStore } from '../stores/model-store';
import { useCompanionStore } from '../stores/companion-store';
import type { SSEFrame } from '../api/sse-parser';
import type {
  ContentBlock, MessageStart, MessageEnd, MessageError,
  ActionEvent, CompanionState, CompanionBubble,
} from '../api/types';

interface _Block {
  type: 'text' | 'think' | 'tool' | 'widget' | 'video';
  content?: string;
  toolName?: string;
  toolCallId?: string;
  status?: 'running' | 'done';
  isError?: boolean;
  widget?: any;
  videoUrl?: string;
  videoSize?: string;
  videoSeconds?: string;
}

export function useSSE() {
  const abortRef = useRef<AbortController | null>(null);
  const blocksRef = useRef<_Block[]>([]);

  const {
    setStreaming, addMessage, setStreamingMessageId,
    appendText, setStreamBlocks,
    setUsage, resetSteps, enqueuePending, dequeuePending,
    addWidget, addAudio, setHitlRequest,
  } = useChatStore();

  const { sessionId, setSessionId, buildAuthHeaders } = useSessionStore();
  const { setWelcomeVisible, setInputValue } = useUIStore();

  // Track blocks in chronological order from v1 SSE events.
  // Internal _Block model is unchanged — status is derived from phase/actionType.
  const processEvent = useCallback((frame: SSEFrame) => {
    const evt = frame.data;
    const blocks = blocksRef.current;
  
    // --- Dispatch by evt.type (message/content/heart/state) or actionType ---
    const type = (evt as any).type as string | undefined;
    const actionType = (evt as any).actionType as string | undefined;
  
    if (type === 'message.start') {
      const e = evt as MessageStart;
      setSessionId(e.sessionId);
    }
    else if (type === 'message.end') {
      const e = evt as MessageEnd;
      setUsage(e.usage);
    }
    else if (type === 'message.error') {
      const e = evt as MessageError;
      addMessage({ id: `err-${Date.now()}`, role: 'error', content: e.error.message || e.error.type, timestamp: Date.now() });
    }
    else if (type === 'heart') {
      // no-op
    }
    else if (type === 'state.snapshot' || type === 'state.delta') {
      // Future: sync agent state
    }
    else if (type === 'step.start' || type === 'step.end') {
      // Future: step visualization
    }
    // -- Content blocks (type is 'text' / 'thinking' / etc.) --
    else if ((evt as any).phase !== undefined) {
      const cb = evt as ContentBlock;
      if (cb.type === 'text') {
        if (cb.phase === 'delta') {
          // Close running think block on first text
          const prev = blocks[blocks.length - 1];
          if (prev && prev.type === 'think' && prev.status === 'running') {
            prev.status = 'done';
          }
          appendText(cb.content);
          if (prev && prev.type === 'text') {
            prev.content += cb.content;
          } else {
            blocks.push({ type: 'text', content: cb.content });
          }
        }
        // phase=start / done: no-op (slot created by delta, done is informational)
      }
      else if (cb.type === 'thinking') {
        if (cb.phase === 'delta') {
          const prev = blocks[blocks.length - 1];
          if (prev && prev.type === 'think' && prev.status === 'running') {
            prev.content += cb.content;
          } else {
            blocks.push({ type: 'think', content: cb.content, status: 'running' });
          }
        }
      }
    }
    // -- Action events (dispatch by actionType) --
    else if (actionType) {
      const ae = evt as ActionEvent;
      switch (actionType) {
        case 'tool_call.started': {
          blocks.push({
            type: 'tool', content: JSON.stringify(ae.arguments),
            toolName: ae.name, toolCallId: ae.toolCallId, status: 'running',
          });
          break;
        }
  
        case 'tool_call.progress':
          // progress updates — currently no-op in UI
          break;
  
        case 'tool_call.completed': {
          const b = blocks.find(blk => blk.toolCallId === ae.toolCallId && blk.type === 'tool');
          const resultOutput = ae.result?.output ?? '';
          const isError = ae.result?.isError ?? false;
          if (b) { b.content = resultOutput; b.status = 'done'; b.isError = isError; }
          if (ae.result?.display?.widget) {
            addWidget(ae.result.display.widget);
            blocks.push({ type: 'widget', widget: ae.result.display.widget as any, status: 'done' });
          }
          if (ae.result?.display?.audio) addAudio(ae.result.display.audio);
          // Detect video URL from result output
          if ((ae.name === 'generate_video' || ae.name === 'check_video_status') && resultOutput) {
            const vm = (resultOutput as string).match(/https?:\/\/\S+\.mp4\b/);
            if (vm) {
              const sm = (resultOutput as string).match(/\u5206\u8fa8\u7387\**:\s*(\S+)/);
              const tm = (resultOutput as string).match(/\u65f6\u957f\**:\s*([\d.]+)s/);
              blocks.push({
                type: 'video',
                content: vm[0],
                videoUrl: vm[0],
                videoSize: sm?.[1],
                videoSeconds: tm?.[1],
                status: 'done',
              } as any);
            }
          }
          break;
        }
  
        case 'human_input.required': {
          setHitlRequest({
            toolCallId: ae.toolCallId!,
            prompt: ae.prompt!,
            inputSchema: ae.inputSchema as any,
          });
          break;
        }
      }
    }
    // -- Companion events (companionType field) --
    else if ((evt as any).companionType) {
      if ((evt as any).companionType === 'state') {
        const ce = evt as CompanionState;
        const { setEmotion } = useCompanionStore.getState();
        setEmotion({
          emotion: ce.emotion,
          eye_override: ce.eyeOverride,
          frontend_mood: ce.frontendMood as any,
        });
      } else if ((evt as any).companionType === 'bubble') {
        const cb = evt as CompanionBubble;
        const { setBubble } = useCompanionStore.getState();
        setBubble({ text: cb.text, ttl_ms: cb.ttlMs });
      }
    }
  
    // Sync live blocks to store for StreamingMessage
    setStreamBlocks(blocksRef.current.map(b => ({
      type: b.type,
      text: b.type === 'text' ? b.content : undefined,
      label: b.type === 'tool' ? b.toolName : undefined,
      detail: b.type === 'video' ? (b as any).videoUrl : b.content,
      isError: b.isError,
      status: b.status as 'running' | 'done' | undefined,
      videoUrl: b.type === 'video' ? (b as any).videoUrl : undefined,
      videoSize: b.type === 'video' ? (b as any).videoSize : undefined,
      videoSeconds: b.type === 'video' ? (b as any).videoSeconds : undefined,
      widget: b.type === 'widget' ? (b as any).widget : undefined,
    } as MessageBlock)));
  }, [appendText, setStreamBlocks, addWidget, addAudio, setHitlRequest, setUsage, addMessage, setSessionId]);

  const _runStream = useCallback(async (text: string) => {
    setStreaming(true);
    resetSteps();
    blocksRef.current = [];
    const assistantId = `asst-${Date.now()}`;
    setStreamingMessageId(assistantId);

    const controller = new AbortController();
    abortRef.current = controller;
    const session = useSessionStore.getState();

    try {
      const authHeaders = session.buildAuthHeaders();
      const personaId = useSessionStore.getState().personaId;
      const modelStore = useModelStore.getState();
      const gen = streamChat(text, session.sessionId, authHeaders, controller.signal, personaId,
        modelStore.currentProvider, modelStore.currentModel);

      for await (const frame of gen) {
        processEvent(frame);
        // Yield to UI after thinking deltas and tool starts
        const d = frame.data as any;
        if (
          (d.type === 'thinking' && d.phase === 'delta') ||
          (d.actionType === 'tool_call.started')
        ) {
          await new Promise((r) => setTimeout(r, 0));
        }
      }

      // Build clean content + self-contained blocks
      const blocks = blocksRef.current;
      for (const b of blocks) {
        if (b.status === 'running') b.status = 'done';
      }

      const contentParts: string[] = [];
      const msgBlocks: import('../stores/chat-store').MessageBlock[] = [];

      for (const b of blocks) {
        const c = b.content || '';
        if (b.type === 'text') {
          contentParts.push(c);
          msgBlocks.push({ type: 'text', text: c });
        } else if (b.type === 'think') {
          msgBlocks.push({ type: 'think', detail: c });
        } else if (b.type === 'tool') {
          msgBlocks.push({ type: 'tool', label: b.toolName, detail: c, isError: b.isError });
        } else if (b.type === 'widget') {
          msgBlocks.push({ type: 'widget', widget: (b as any).widget });
        } else if (b.type === 'video') {
          msgBlocks.push({
            type: 'video',
            videoUrl: (b as any).videoUrl,
            videoSize: (b as any).videoSize,
            videoSeconds: (b as any).videoSeconds,
            detail: (b as any).videoUrl,
          });
        }
      }
      const content = contentParts.join('').trim() || '(empty)';

      const finalState = useChatStore.getState();
      addMessage({
        id: assistantId, role: 'assistant', content,
        blocks: msgBlocks.length > 0 ? msgBlocks : undefined,
        widgets: finalState.widgets.length > 0 ? [...finalState.widgets] : undefined,
        audios: finalState.audios.length > 0 ? [...finalState.audios] : undefined,
        usage: finalState.usage,
        timestamp: Date.now(),
      });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : String(err);
      useToastStore.getState().addToast(msg, 'error');
      addMessage({ id: `err-${Date.now()}`, role: 'error', content: msg, timestamp: Date.now() });
    } finally {
      setStreaming(false);
      setStreamingMessageId(null);
      abortRef.current = null;
      setTimeout(() => { resetSteps(); }, 350);
      const pending = dequeuePending();
      if (pending) { setTimeout(() => _runStream(pending), 100); }
    }
  }, [setStreaming, setStreamingMessageId, addMessage, dequeuePending, processEvent, resetSteps]);

  const sendMessage = useCallback((text: string) => {
    if (!text.trim()) return;
    setWelcomeVisible(false);
    setInputValue('');
    addMessage({ id: `user-${Date.now()}`, role: 'user', content: text, timestamp: Date.now() });

    const store = useChatStore.getState();
    if (store.isStreaming) { enqueuePending(text); return; }
    _runStream(text);
  }, [addMessage, enqueuePending, _runStream, setWelcomeVisible, setInputValue]);

  const abort = useCallback(async () => {
    abortRef.current?.abort();
    const sid = useSessionStore.getState().sessionId;
    if (sid) { try { await abortSession(sid); } catch { /* best-effort */ } }
  }, []);

  return { sendMessage, abort };
}
