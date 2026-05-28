import { useRef, useCallback } from 'react';
import { streamChat, abortSession } from '../api/client';
import { useChatStore } from '../stores/chat-store';
import { useSessionStore } from '../stores/session-store';
import { useUIStore } from '../stores/ui-store';
import { getDisplayableText, extractThinkSteps, getStreamingThinkContent } from '../utils/think';
import type { SSEEvent } from '../api/types';
import type { ToolStep, HitlRequest } from '../stores/chat-store';

const SLOW_TOOL_RE = /music|text_to_music/;

export function useSSE() {
  const abortRef = useRef<AbortController | null>(null);
  const stepTimers = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());
  const seenThinks = useRef<Set<string>>(new Set());
  const thinkingStepId = useRef<string | null>(null);
  // Tracks the streaming think step created from <think> tags in text (non-Anthropic path)
  const streamingThinkTextId = useRef<string | null>(null);
  // Monotonic counter so each streaming think block gets a unique ID
  const thinkTextSeq = useRef(0);

  const {
    setStreaming, addMessage, setStreamingMessageId,
    appendText, appendThinking,
    addStep, updateStep, findRunningStep,
    setUsage, resetSteps, enqueuePending, dequeuePending,
    addWidget, addAudio, setHitlRequest,
  } = useChatStore();

  const { sessionId, setSessionId, buildAuthHeaders } = useSessionStore();
  const { setWelcomeVisible, setInputValue } = useUIStore();

  const processEvent = useCallback((evt: SSEEvent) => {
    switch (evt.event) {
      case 'session_id':
        setSessionId(evt.session_id);
        break;

      case 'thinking_delta':
        appendThinking(evt.text);
        if (!thinkingStepId.current) {
          thinkingStepId.current = 'think-stream';
          addStep({
            id: thinkingStepId.current,
            type: 'think',
            label: '思考过程',
            detail: evt.text,
            renderedDetail: '',
            status: 'running',
            isError: false,
            isSlow: false,
            startTime: Date.now(),
            toolCallId: '',
          });
        } else {
          updateStep(thinkingStepId.current, {
            detail: useChatStore.getState().thinkingText,
          });
        }
        break;

      case 'text_delta': {
        // Close Anthropic-native thinking step on first text
        if (thinkingStepId.current) {
          updateStep(thinkingStepId.current, { status: 'done' });
          thinkingStepId.current = null;
        }
        appendText(evt.text);

        const currentText = useChatStore.getState().currentText;

        // 1. Handle streaming partial <think> block
        const streamContent = getStreamingThinkContent(currentText);
        if (streamContent !== null) {
          // Inside an unclosed <think> — create or update running step
          if (!streamingThinkTextId.current) {
            const id = `think-text-${thinkTextSeq.current++}`;
            streamingThinkTextId.current = id;
            addStep({
              id,
              type: 'think',
              label: '思考过程',
              detail: streamContent,
              renderedDetail: '',
              status: 'running',
              isError: false,
              isSlow: false,
              startTime: Date.now(),
              toolCallId: '',
            });
          } else {
            updateStep(streamingThinkTextId.current, {
              detail: streamContent,
            });
          }
        } else if (streamingThinkTextId.current) {
          // Block just completed — pull the correct content from currentText
          // (the step's last detail may include partial closing-tag chunks)
          const tempSeen = new Set<string>();
          const allBlocks = extractThinkSteps(currentText, tempSeen);
          const lastBlock = allBlocks.length > 0 ? allBlocks[allBlocks.length - 1] : null;
          if (lastBlock) {
            seenThinks.current.add(lastBlock.content);
            updateStep(streamingThinkTextId.current, {
              detail: lastBlock.content,
              status: 'done',
            });
          } else {
            updateStep(streamingThinkTextId.current, { status: 'done' });
          }
          streamingThinkTextId.current = null;
        }

        // 2. Extract complete <think> blocks (skips already-seen via seenThinks)
        const completeBlocks = extractThinkSteps(currentText, seenThinks.current);
        for (const block of completeBlocks) {
          addStep({
            id: `think-${seenThinks.current.size}`,
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
        break;
      }

      case 'tool_start': {
        const step: ToolStep = {
          id: `step-${evt.tool_call_id}`,
          type: 'tool',
          label: evt.tool_name,
          detail: JSON.stringify(evt.args),
          renderedDetail: '',
          status: 'running',
          isError: false,
          isSlow: SLOW_TOOL_RE.test(evt.tool_name),
          startTime: Date.now(),
          toolCallId: evt.tool_call_id,
        };
        addStep(step);
        const timer = setInterval(() => {
          // re-render via store subscription
        }, 1000);
        stepTimers.current.set(step.id, timer);
        break;
      }

      case 'tool_update': {
        const running = findRunningStep();
        if (running) {
          updateStep(running.id, {
            detail: evt.result,
            renderedDetail: evt.result,
          });
        }
        break;
      }

      case 'tool_end': {
        const { steps: currentSteps } = useChatStore.getState();
        const step = currentSteps.find(s => s.toolCallId === evt.tool_call_id);
        if (step) {
          if (stepTimers.current.has(step.id)) {
            clearInterval(stepTimers.current.get(step.id));
            stepTimers.current.delete(step.id);
          }
          updateStep(step.id, {
            status: 'done',
            detail: evt.result,
            renderedDetail: evt.result,
            isError: evt.is_error,
          });
        }
        if (evt.display?.widget) addWidget(evt.display.widget);
        if (evt.display?.audio) addAudio(evt.display.audio);
        break;
      }

      case 'message_end':
        setUsage(evt.usage);
        break;

      case 'human_input_required': {
        const req: HitlRequest = {
          toolCallId: evt.tool_call_id,
          prompt: evt.prompt,
          inputSchema: evt.input_schema,
        };
        setHitlRequest(req);
        break;
      }

      case 'error':
        addMessage({
          id: `err-${Date.now()}`,
          role: 'error',
          content: evt.message,
          timestamp: Date.now(),
        });
        break;

      case 'done':
        break;
    }
  }, [appendText, appendThinking, addStep, updateStep, findRunningStep, addWidget, addAudio, setHitlRequest, setUsage, addMessage, setSessionId]);

  // Internal: run SSE stream without adding user message (caller handles that)
  const _runStream = useCallback(async (text: string) => {
    setStreaming(true);
    resetSteps();
    seenThinks.current.clear();
    thinkingStepId.current = null;
    streamingThinkTextId.current = null;
    thinkTextSeq.current = 0;
    const assistantId = `asst-${Date.now()}`;
    setStreamingMessageId(assistantId);

    const controller = new AbortController();
    abortRef.current = controller;
    const session = useSessionStore.getState();

    try {
      const authHeaders = session.buildAuthHeaders();
      const gen = streamChat(text, session.sessionId, authHeaders, controller.signal);

      for await (const evt of gen) {
        processEvent(evt);
        // Yield to React after step-creation events so the UI renders
        // before the next event arrives (prevents "flash" of batched steps)
        if (evt.event === 'thinking_delta' || evt.event === 'tool_start'
            || (evt.event === 'text_delta' && streamingThinkTextId.current)) {
          await new Promise((r) => setTimeout(r, 0));
        }
      }

      const finalState = useChatStore.getState();
      const rawText = finalState.currentText || finalState.thinkingText || '(empty)';
      const content = getDisplayableText(rawText) || rawText;
      addMessage({
        id: assistantId,
        role: 'assistant',
        content,
        rawContent: content,
        steps: finalState.steps.length > 0 ? [...finalState.steps] : undefined,
        widgets: finalState.widgets.length > 0 ? [...finalState.widgets] : undefined,
        audios: finalState.audios.length > 0 ? [...finalState.audios] : undefined,
        usage: finalState.usage,
        timestamp: Date.now(),
      });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : String(err);
      addMessage({
        id: `err-${Date.now()}`,
        role: 'error',
        content: msg,
        timestamp: Date.now(),
      });
    } finally {
      setStreaming(false);
      setStreamingMessageId(null);
      abortRef.current = null;

      stepTimers.current.forEach((t) => clearInterval(t));
      stepTimers.current.clear();

      // Delay reset so StreamingMessage can render markdown and fade out
      // before MessageBubble takes over.
      setTimeout(() => {
        resetSteps();
      }, 350);

      // Drain pending queue — user message already shown when first enqueued
      const pending = dequeuePending();
      if (pending) {
        setTimeout(() => _runStream(pending), 100);
      }
    }
  }, [setStreaming, resetSteps, setStreamingMessageId, addMessage, setUsage, setStreaming, dequeuePending, processEvent]);

  const sendMessage = useCallback((text: string) => {
    if (!text.trim()) return;

    setWelcomeVisible(false);
    setInputValue('');

    const store = useChatStore.getState();

    // Show user message immediately
    addMessage({
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: Date.now(),
    });

    if (store.isStreaming) {
      enqueuePending(text);
      return;
    }

    _runStream(text);
  }, [addMessage, enqueuePending, _runStream, setWelcomeVisible, setInputValue]);

  const abort = useCallback(async () => {
    abortRef.current?.abort();
    const sid = useSessionStore.getState().sessionId;
    if (sid) {
      try { await abortSession(sid); } catch { /* best-effort */ }
    }
  }, []);

  return { sendMessage, abort };
}
