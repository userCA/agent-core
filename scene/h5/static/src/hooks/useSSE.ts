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
  ContentBlock, ContentBlockInput, MessageStart, MessageEnd, MessageError,
  ActionEvent, CompanionState, CompanionBubble,
} from '../api/types';

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const commaIdx = result.indexOf(',');
      resolve(commaIdx >= 0 ? result.slice(commaIdx + 1) : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function filesToContentBlocks(files: File[]): Promise<ContentBlockInput[]> {
  const blocks: ContentBlockInput[] = [];
  for (const file of files) {
    const b64 = await fileToBase64(file);
    const ext = file.name.split('.').pop()?.toLowerCase() || 'png';
    const typeMap: Record<string, ContentBlockInput['type']> = {
      png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image', svg: 'image',
      mp3: 'audio', wav: 'audio', ogg: 'audio',
      mp4: 'video', webm: 'video',
    };
    blocks.push({
      type: typeMap[ext] || 'file',
      content: b64,
      meta: { format: ext, filename: file.name, size: file.size },
    });
  }
  return blocks;
}

interface _Block {
  type: 'text' | 'think' | 'tool' | 'widget' | 'video' | 'image' | 'file' | 'skill';
  content?: string;
  toolName?: string;
  toolCallId?: string;
  status?: 'running' | 'done';
  isError?: boolean;
  turnPhase?: 'intermediate' | 'final';
  widget?: any;
  videoUrl?: string;
  videoSize?: string;
  videoSeconds?: string;
  imageUrl?: string;
  imageMeta?: { width?: number; height?: number; format?: string; size?: string };
  fileUrl?: string;
  fileName?: string;
  fileSize?: string;
}

export function useSSE() {
  const abortRef = useRef<AbortController | null>(null);
  const blocksRef = useRef<_Block[]>([]);
  const errorShownRef = useRef(false);
  const _blocksDirtyRef = useRef(false);
  const turnStartIdxRef = useRef(0);
  // Current phase for blocks being created — ensures between-turn blocks (tool execution) get tagged
  const currentTurnPhaseRef = useRef<'intermediate' | 'final'>('intermediate');

  const {
    setStreaming, addMessage, setStreamingMessageId,
    appendText, setStreamBlocks,
    setUsage, resetSteps, enqueuePending, dequeuePending,
    addWidget, addAudio, setHitlRequest,
  } = useChatStore();

  const { sessionId, setSessionId, buildAuthHeaders } = useSessionStore();
  const { setWelcomeVisible, setInputValue } = useUIStore();

  // Throttled block sync — only push to React state once per animation frame
  const _flushPending = useCallback(() => {
    _blocksDirtyRef.current = false;
    const blocks = blocksRef.current;
    setStreamBlocks(blocks.map(b => ({
      type: b.type === 'file' ? 'text' : b.type as MessageBlock['type'],
      text: b.type === 'text' ? b.content : undefined,
      label: b.type === 'tool' ? b.toolName : b.type === 'skill' ? b.toolName : undefined,
      detail: b.type === 'video' ? b.videoUrl : b.type === 'image' ? b.imageUrl : b.type === 'file' ? b.fileUrl : b.content,
      isError: b.isError,
      status: b.status,
      turnPhase: b.turnPhase,
      videoUrl: b.type === 'video' ? b.videoUrl : undefined,
      videoSize: b.type === 'video' ? b.videoSize : undefined,
      videoSeconds: b.type === 'video' ? b.videoSeconds : undefined,
      widget: b.type === 'widget' ? b.widget : undefined,
      imageUrl: b.type === 'image' ? b.imageUrl : undefined,
      imageMeta: b.type === 'image' ? b.imageMeta : undefined,
    } as MessageBlock)));
  }, [setStreamBlocks]);

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
      // Mark turn boundary — blocks from this index belong to the new turn
      turnStartIdxRef.current = blocksRef.current.length;
      // New LLM turn always starts as intermediate until message.end says otherwise
      currentTurnPhaseRef.current = 'intermediate';
    }
    else if (type === 'message.end') {
      const e = evt as MessageEnd;
      setUsage(e.usage);
      // Back-tag current turn's blocks based on stopReason
      const phase: 'intermediate' | 'final' = e.stopReason === 'end_turn' ? 'final' : 'intermediate';
      for (let i = turnStartIdxRef.current; i < blocks.length; i++) {
        blocks[i].turnPhase = phase;
      }
      // Update current phase — blocks created between turns (tool execution) inherit this
      currentTurnPhaseRef.current = phase;
      // Detect error stop reason and show toast (error bubble comes from message.error)
      if (e.stopReason === 'error' && !errorShownRef.current) {
        errorShownRef.current = true;
        const errMsg = '服务暂时不可用，请稍后重试';
        useToastStore.getState().addToast(errMsg, 'error');
        addMessage({ id: `err-${Date.now()}`, role: 'error', content: errMsg, timestamp: Date.now() });
      }
    }
    else if (type === 'message.error') {
      const e = evt as MessageError;
      const rawMsg = e.error.message || e.error.type;
      // Translate known error patterns to user-friendly Chinese
      let friendly = rawMsg;
      if (rawMsg.includes('rate_limit') || rawMsg.includes('429') || rawMsg.includes('用量上限') || rawMsg.includes('用量上限')) {
        friendly = '请求过于频繁，请稍后再试';
      } else if (rawMsg.includes('500') || rawMsg.includes('Internal Server Error')) {
        friendly = '服务暂时不可用，请稍后重试';
      } else if (rawMsg.includes('timeout') || rawMsg.includes('Timeout')) {
        friendly = '请求超时，请检查网络后重试';
      } else if (rawMsg.includes('auth') || rawMsg.includes('API key') || rawMsg.includes('Unauthorized')) {
        friendly = '认证失败，请检查 API 设置';
      }
      if (!errorShownRef.current) {
        errorShownRef.current = true;
        addMessage({ id: `err-${Date.now()}`, role: 'error', content: friendly, timestamp: Date.now() });
      }
    }
    else if (type === 'heart') {
      // no-op
    }
    else if (type === 'state.snapshot' || type === 'state.delta') {
      // Future: sync agent state
    }
    // -- Content blocks (phase field present) --
    // SSE v1 spec: three-phase lifecycle start → delta×N → done
    else if ((evt as any).phase !== undefined) {
      const cb = evt as ContentBlock;
      if (cb.type === 'text') {
        if (cb.phase === 'start') {
          // Close running think block when text starts
          const prev = blocks[blocks.length - 1];
          if (prev && prev.type === 'think' && prev.status === 'running') {
            prev.status = 'done';
          }
          // Create text slot per spec — content is empty
          blocks.push({ type: 'text', content: '' });
        } else if (cb.phase === 'delta') {
          // Append delta to last text block, or create if missing (backward compat)
          const prev = blocks[blocks.length - 1];
          if (prev && prev.type === 'text') {
            prev.content = (prev.content || '') + cb.content;
          } else {
            blocks.push({ type: 'text', content: cb.content });
          }
          appendText(cb.content);
        }
        // phase=done: text block complete — no-op (content already assembled via deltas)
      }
      else if (cb.type === 'thinking') {
        if (cb.phase === 'start') {
          blocks.push({ type: 'think', content: '', status: 'running' });
        } else if (cb.phase === 'delta') {
          const prev = blocks[blocks.length - 1];
          if (prev && prev.type === 'think' && prev.status === 'running') {
            prev.content = (prev.content || '') + cb.content;
          } else {
            blocks.push({ type: 'think', content: cb.content, status: 'running' });
          }
        } else if (cb.phase === 'done') {
          const prev = blocks[blocks.length - 1];
          if (prev && prev.type === 'think' && prev.status === 'running') {
            prev.status = 'done';
          }
        }
      }
      // Non-text content blocks (image/audio/video/file/component) — snapshot mode: start + done
      else if (cb.phase === 'done') {
        const contentUrl = cb.content || '';
        if (cb.type === 'image') {
          // Push as dedicated image block (not markdown text)
          blocks.push({
            type: 'image',
            content: contentUrl,
            imageUrl: contentUrl,
            imageMeta: {
              width: (cb.meta as any)?.width,
              height: (cb.meta as any)?.height,
              format: (cb.meta as any)?.format,
              size: (cb.meta as any)?.size,
            },
            status: 'done',
          } as any);
          // Do NOT appendText — backend already strips image markdown from text stream
        } else if (cb.type === 'video') {
          blocks.push({
            type: 'video' as any, content: contentUrl,
            videoUrl: contentUrl,
            videoSize: (cb.meta as any)?.size,
            videoSeconds: (cb.meta as any)?.duration ? String((cb.meta as any).duration / 1000) : undefined,
            status: 'done',
          } as any);
        } else if (cb.type === 'audio') {
          if ((cb.meta as any)?.urls) {
            addAudio({ urls: (cb.meta as any).urls, task_id: (cb.meta as any)?.task_id });
          }
        }
        else if (cb.type === 'component') {
          // Widget component — meta carries the widget display data
          if (cb.meta) {
            addWidget({ version: 1, html: String(cb.meta.html || ''), title: cb.meta.title as string, height: cb.meta.height as number });
            blocks.push({ type: 'widget', widget: { version: 1, html: String(cb.meta.html || ''), title: cb.meta.title as string, height: cb.meta.height as number }, status: 'done' });
          }
        }
        else if (cb.type === 'file') {
          blocks.push({
            type: 'file',
            content: contentUrl,
            fileUrl: contentUrl,
            fileName: (cb.meta as any)?.name || 'file',
            fileSize: (cb.meta as any)?.size,
            status: 'done',
          });
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
            toolName: ae.name || ae.toolCallId || 'tool', toolCallId: ae.toolCallId, status: 'running',
          });
          break;
        }
  
        case 'tool_call.progress':
          // progress updates — currently no-op in UI
          break;
        
        case 'skill.started': {
          blocks.push({
            type: 'skill',
            content: ae.skillDescription || ae.skillName || ae.skillId,
            toolName: ae.skillName || ae.skillId,
            status: 'running',
          });
          break;
        }

        case 'skill.completed': {
          const sb = [...blocks].reverse().find(blk => blk.type === 'skill' && blk.toolName === ae.skillId && blk.status === 'running');
          if (sb) sb.status = 'done';
          break;
        }

        case 'step.start':
        case 'step.end':
          // Future: step visualization
          break;
        
        case 'tool_call.completed': {
          const b = blocks.find(blk => blk.toolCallId === ae.toolCallId && blk.type === 'tool');
          const resultOutput = ae.result?.output ?? '';
          const isError = ae.result?.isError ?? false;
          if (b) { b.content = resultOutput; b.status = 'done'; b.isError = isError; }
          if (ae.result?.display?.widget) {
            addWidget(ae.result.display.widget);
            blocks.push({ type: 'widget', widget: ae.result.display.widget, status: 'done' });
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

        case 'human_input.submitted': {
          // User submitted HITL input — dismiss the card
          setHitlRequest(null);
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

    // Tag any untagged blocks (e.g. tool execution results between turns)
    for (let i = 0; i < blocks.length; i++) {
      if (!blocks[i].turnPhase) blocks[i].turnPhase = currentTurnPhaseRef.current;
    }

    // Sync blocks to store (throttled, skip for text deltas — streamText already triggers re-render)
    const isTextDelta = (type === 'text' && (evt as any).phase === 'delta');
    if (!isTextDelta) {
      _blocksDirtyRef.current = true;
    }
    if (_blocksDirtyRef.current && !isTextDelta) {
      if (typeof requestAnimationFrame !== 'undefined') {
        requestAnimationFrame(_flushPending);
      } else {
        _flushPending();
      }
    }
  }, [appendText, _flushPending, addWidget, addAudio, setHitlRequest, setUsage, addMessage, setSessionId]);

  const _runStream = useCallback(async (text: string, files?: File[]) => {
    setStreaming(true);
    resetSteps();
    blocksRef.current = [];
    errorShownRef.current = false;
    turnStartIdxRef.current = 0;
    currentTurnPhaseRef.current = 'intermediate';
    const assistantId = `asst-${Date.now()}`;
    setStreamingMessageId(assistantId);

    const controller = new AbortController();
    abortRef.current = controller;
    const session = useSessionStore.getState();

    try {
      const authHeaders = session.buildAuthHeaders();
      const personaId = useSessionStore.getState().personaId;
      const modelStore = useModelStore.getState();
      const contentBlocks = files && files.length > 0 ? await filesToContentBlocks(files) : undefined;
      const gen = streamChat(text, session.sessionId, authHeaders, controller.signal, personaId,
        modelStore.currentProvider, modelStore.currentModel, contentBlocks);

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

      // Final flush of any pending dirty blocks
      _flushPending();

      // Build clean content + self-contained blocks
      const blocks = blocksRef.current;
      for (const b of blocks) {
        if (b.status === 'running') b.status = 'done';
      }

      const contentParts: string[] = [];
      const intermediateBlocks: import('../stores/chat-store').MessageBlock[] = [];
      const finalBlocks: import('../stores/chat-store').MessageBlock[] = [];

      for (const b of blocks) {
        const c = b.content || '';
        let mb: import('../stores/chat-store').MessageBlock | null = null;
        if (b.type === 'text') {
          contentParts.push(c);
          mb = { type: 'text', text: c };
        } else if (b.type === 'think') {
          mb = { type: 'think', detail: c };
        } else if (b.type === 'tool') {
          mb = { type: 'tool', label: b.toolName, detail: c, isError: b.isError };
        } else if (b.type === 'skill') {
          mb = { type: 'skill', label: b.toolName, detail: b.content };
        } else if (b.type === 'widget') {
          mb = { type: 'widget', widget: b.widget };
        } else if (b.type === 'video') {
          mb = {
            type: 'video',
            videoUrl: b.videoUrl,
            videoSize: b.videoSize,
            videoSeconds: b.videoSeconds,
            detail: b.videoUrl,
          };
        } else if (b.type === 'image') {
          mb = {
            type: 'image',
            imageUrl: b.imageUrl,
            imageMeta: b.imageMeta,
            detail: b.imageUrl,
          };
        }
        if (mb) {
          // Route by turnPhase: intermediate → trace card, final → content card
          if (b.turnPhase === 'intermediate') {
            intermediateBlocks.push(mb);
          } else {
            finalBlocks.push(mb);
          }
        }
      }
      // Content text comes from final text blocks only
      let content = contentParts.join('').trim();
      if (!content) {
        const hasMedia = finalBlocks.some(b => b.type === 'image' || b.type === 'video' || b.type === 'widget');
        content = hasMedia ? '已生成媒体内容' : '(empty)';
      }

      // Skip adding empty assistant message when there was an error and no content
      const hasError = blocksRef.current.length === 0 && content === '(empty)';
      if (hasError) {
        // Error message was already added by message.error or message.end handler
        return;
      }

      const allBlocks = [...intermediateBlocks, ...finalBlocks];
      const finalState = useChatStore.getState();
      addMessage({
        id: assistantId, role: 'assistant', content,
        blocks: allBlocks.length > 0 ? allBlocks : undefined,
        intermediateBlocks: intermediateBlocks.length > 0 ? intermediateBlocks : undefined,
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
      // Clear text immediately so finalized message appears without delay
      useChatStore.setState({ currentText: '' });
      // Defer remaining cleanup (blocks/widgets/audios) for fade-out
      setTimeout(() => { resetSteps(); }, 260);
      const pending = dequeuePending();
      if (pending) { setTimeout(() => _runStream(pending), 100); }
    }
  }, [setStreaming, setStreamingMessageId, addMessage, dequeuePending, processEvent, resetSteps, _flushPending]);

  const sendMessage = useCallback((text: string, files?: File[]) => {
    if (!text.trim() && (!files || files.length === 0)) return;
    setWelcomeVisible(false);
    setInputValue('');

    // Build preview URLs for image files (displayed in user message bubble)
    const previewUrls = files
      ?.filter(f => f.type.startsWith('image/'))
      .map(f => URL.createObjectURL(f)) ?? [];
    addMessage({
      id: `user-${Date.now()}`,
      role: 'user',
      content: text || '(图片)',
      attachments: previewUrls.length > 0 ? previewUrls : undefined,
      timestamp: Date.now(),
    });

    const store = useChatStore.getState();
    if (store.isStreaming) { enqueuePending(text); return; }
    _runStream(text, files);
  }, [addMessage, enqueuePending, _runStream, setWelcomeVisible, setInputValue]);

  const abort = useCallback(async () => {
    abortRef.current?.abort();
    const sid = useSessionStore.getState().sessionId;
    if (sid) { try { await abortSession(sid); } catch { /* best-effort */ } }
  }, []);

  return { sendMessage, abort };
}
