import { useRef, useCallback } from 'react';
import { streamChat, abortSession } from '../api/client';
import { useChatStore, type HitlRequest, type MessageBlock } from '../stores/chat-store';
import { useSessionStore } from '../stores/session-store';
import { useUIStore } from '../stores/ui-store';
import { useToastStore } from '../stores/toast-store';
import { useModelStore } from '../stores/model-store';
import { useCompanionStore } from '../stores/companion-store';
import { getDisplayableText } from '../utils/think';
import type { SSEEvent } from '../api/types';

interface _DelegationAgent {
  agent: string;
  status: 'running' | 'completed' | 'failed' | 'aborted';
  task?: string;
  summary?: string;
}

interface _PlanStep {
  id: string;
  title: string;
  status: string;
  detail?: string | null;
}

interface _Block {
  type: 'text' | 'think' | 'tool' | 'widget' | 'video' | 'delegation' | 'plan' | 'workflow';
  content?: string;
  toolName?: string;
  toolCallId?: string;
  status?: 'running' | 'done';
  isError?: boolean;
  widget?: any;
  videoUrl?: string;
  videoSize?: string;
  videoSeconds?: string;
  mode?: string;
  delegationId?: string;
  agents?: _DelegationAgent[];
  planId?: string;
  planTitle?: string;
  planStatus?: string;
  planDone?: number;
  planTotal?: number;
  planSteps?: _PlanStep[];
  workflowRunId?: string;
  workflowName?: string;
  workflowStatus?: string;
  workflowPhase?: string | null;
  workflowPhases?: string[];
  workflowLog?: string[];
  workflowCompletedAgents?: number;
  workflowTotalAgents?: number;
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

  // Track blocks in chronological order from raw SSE events.
  // At stream end, serialize to content as <details> HTML so structure
  // survives session persistence and renders correctly from history.
  const processEvent = useCallback((evt: SSEEvent) => {
    const blocks = blocksRef.current;

    switch (evt.event) {
      case 'session_id':
        setSessionId(evt.session_id);
        break;

      case 'thinking_delta': {
        const prev = blocks[blocks.length - 1];
        if (prev && prev.type === 'think' && prev.status === 'running') {
          prev.content += evt.text;
        } else {
          blocks.push({ type: 'think', content: evt.text, status: 'running' });
        }
        break;
      }

      case 'text_delta': {
        // Close running think block on first text
        const prev = blocks[blocks.length - 1];
        if (prev && prev.type === 'think' && prev.status === 'running') {
          prev.status = 'done';
        }
        appendText(evt.text);
        if (prev && prev.type === 'text') {
          prev.content += evt.text;
        } else {
          blocks.push({ type: 'text', content: evt.text });
        }
        break;
      }

      case 'tool_start': {
        // Special tools use dedicated cards instead of generic tool cards.
        if (evt.tool_name === 'delegate_task' || evt.tool_name === 'manage_plan' || evt.tool_name === 'run_workflow') break;
        blocks.push({
          type: 'tool', content: JSON.stringify(evt.args),
          toolName: evt.tool_name, toolCallId: evt.tool_call_id, status: 'running',
        });
        break;
      }

      case 'tool_update':
        break;

      case 'delegation': {
        let block = blocks.find(
          (blk) => blk.type === 'delegation' && blk.delegationId === evt.delegation_id,
        );
        if (!block) {
          block = {
            type: 'delegation',
            delegationId: evt.delegation_id,
            mode: evt.mode,
            status: 'running',
            agents: [],
          };
          blocks.push(block);
        }
        if (evt.mode) block.mode = evt.mode;
        if (evt.phase === 'agent_start' && evt.agent) {
          const agents = block.agents || (block.agents = []);
          const existing = agents.find((a) => a.agent === evt.agent && a.task === evt.task);
          if (existing) {
            existing.status = 'running';
            existing.task = evt.task;
          } else {
            agents.push({ agent: evt.agent, status: 'running', task: evt.task });
          }
        }
        if (evt.phase === 'agent_end' && evt.agent) {
          const agents = block.agents || (block.agents = []);
          let item = agents.find((a) => a.agent === evt.agent && (a.task === evt.task || !evt.task));
          if (!item) {
            item = { agent: evt.agent, status: 'completed', task: evt.task };
            agents.push(item);
          }
          item.status = (evt.status as _DelegationAgent['status']) || 'completed';
          if (evt.summary) item.summary = evt.summary;
        }
        if (evt.phase === 'end') {
          block.status = 'done';
          block.isError = evt.status === 'failed' || evt.status === 'aborted';
        }
        break;
      }

      case 'plan': {
        const plan = evt.plan;
        const planId = plan?.id;
        let block = blocks.find(
          (blk) => blk.type === 'plan' && (planId ? blk.planId === planId : true),
        );
        if (!block) {
          block = { type: 'plan', planId, status: 'running', planSteps: [] };
          blocks.push(block);
        }
        if (planId) block.planId = planId;
        if (plan) {
          block.planTitle = plan.title;
          block.planStatus = plan.status;
          block.planSteps = plan.steps || [];
        }
        if (typeof evt.done === 'number') block.planDone = evt.done;
        if (typeof evt.total === 'number') block.planTotal = evt.total;
        const terminal =
          evt.phase === 'completed' ||
          evt.phase === 'cancelled' ||
          evt.phase === 'error' ||
          plan?.status === 'completed' ||
          plan?.status === 'cancelled';
        block.status = terminal ? 'done' : 'running';
        block.isError = evt.phase === 'error';
        break;
      }

      case 'workflow': {
        let block = blocks.find(
          (blk) => blk.type === 'workflow' && blk.workflowRunId === evt.run_id,
        );
        if (!block) {
          block = {
            type: 'workflow',
            workflowRunId: evt.run_id,
            status: 'running',
            workflowLog: [],
            workflowPhases: [],
          };
          blocks.push(block);
        }
        if (evt.run_id) block.workflowRunId = evt.run_id;
        if (evt.name) block.workflowName = evt.name;
        if (evt.status) block.workflowStatus = evt.status;
        if (evt.phase !== undefined) block.workflowPhase = evt.phase;
        if (evt.phases && evt.phases.length > 0) block.workflowPhases = evt.phases;
        if (evt.log) block.workflowLog = evt.log;
        if (evt.progress?.completed_agents !== undefined) {
          block.workflowCompletedAgents = evt.progress.completed_agents;
        }
        if (evt.progress?.total_agents !== undefined) {
          block.workflowTotalAgents = evt.progress.total_agents;
        }
        const terminal = evt.status === 'completed' || evt.status === 'failed' || evt.status === 'aborted';
        block.status = terminal ? 'done' : 'running';
        block.isError = evt.status === 'failed' || evt.status === 'aborted';
        break;
      }

      case 'tool_end': {
        if (evt.tool_name === 'delegate_task' || evt.tool_name === 'manage_plan' || evt.tool_name === 'run_workflow') break;
        const b = blocks.find(blk => blk.toolCallId === evt.tool_call_id && blk.type === 'tool');
        if (b) { b.content = evt.result; b.status = 'done'; b.isError = evt.is_error; }
        if (evt.display?.widget) {
          addWidget(evt.display.widget);
          blocks.push({ type: 'widget', widget: evt.display.widget as any, status: 'done' });
        }
        if (evt.display?.audio) addAudio(evt.display.audio);
        // Detect video URL from result text (frontend parses instead of relying on display field)
        if ((evt.tool_name === 'generate_video' || evt.tool_name === 'check_video_status' || evt.tool_name === 'create_short_drama' || evt.tool_name === 'concat_videos') && evt.result) {
          const vm = (evt.result as string).match(/https?:\/\/\S+\.mp4\b/) ||
            (evt.result as string).match(/(\/renders\/\S+\.mp4)/);
          if (vm) {
            const videoUrl = vm[0].startsWith('/') ? `${window.location.origin}${vm[0]}` : vm[0];
            const sm = (evt.result as string).match(/分辨率\**:\s*(\S+)/);
            const tm = (evt.result as string).match(/时长\**:\s*([\d.]+)s/);
            blocks.push({
              type: 'video',
              content: videoUrl,
              videoUrl: videoUrl,
              videoSize: sm?.[1],
              videoSeconds: tm?.[1],
              status: 'done',
            } as any);
          }
        }
        break;
      }

      case 'message_end':
        setUsage(evt.usage);
        break;

      case 'human_input_required':
        setHitlRequest({ toolCallId: evt.tool_call_id, prompt: evt.prompt, inputSchema: evt.input_schema });
        break;

      case 'error':
        addMessage({ id: `err-${Date.now()}`, role: 'error', content: evt.message, timestamp: Date.now() });
        break;

      case 'companion': {
        const { setEmotion } = useCompanionStore.getState();
        setEmotion({
          emotion: evt.emotion,
          eye_override: evt.eye_override,
          frontend_mood: evt.frontend_mood as any,
        });
        break;
      }

      case 'companion_bubble': {
        const { setBubble } = useCompanionStore.getState();
        setBubble({ text: evt.text, ttl_ms: evt.ttl_ms });
        break;
      }
    }
    // Sync live blocks to store for StreamingMessage
    setStreamBlocks(blocksRef.current.map(b => ({
      type: b.type,
      text: b.type === 'text' ? b.content : undefined,
      label: b.type === 'tool' ? b.toolName
        : b.type === 'delegation' ? '协调专家'
        : b.type === 'plan' ? (b.planTitle || '执行计划')
        : undefined,
      detail: b.type === 'video' ? (b as any).videoUrl : b.content,
      isError: b.isError,
      status: b.status as 'running' | 'done' | undefined,
      videoUrl: b.type === 'video' ? (b as any).videoUrl : undefined,
      videoSize: b.type === 'video' ? (b as any).videoSize : undefined,
      videoSeconds: b.type === 'video' ? (b as any).videoSeconds : undefined,
      widget: b.type === 'widget' ? (b as any).widget : undefined,
      mode: b.type === 'delegation' ? b.mode : undefined,
      agents: b.type === 'delegation' ? b.agents : undefined,
      planId: b.type === 'plan' ? b.planId : undefined,
      planTitle: b.type === 'plan' ? b.planTitle : undefined,
      planStatus: b.type === 'plan' ? b.planStatus : undefined,
      planDone: b.type === 'plan' ? b.planDone : undefined,
      planTotal: b.type === 'plan' ? b.planTotal : undefined,
      planSteps: b.type === 'plan' ? b.planSteps : undefined,
      workflowRunId: b.type === 'workflow' ? b.workflowRunId : undefined,
      workflowName: b.type === 'workflow' ? b.workflowName : undefined,
      workflowStatus: b.type === 'workflow' ? b.workflowStatus : undefined,
      workflowPhase: b.type === 'workflow' ? b.workflowPhase : undefined,
      workflowPhases: b.type === 'workflow' ? b.workflowPhases : undefined,
      workflowLog: b.type === 'workflow' ? b.workflowLog : undefined,
      workflowCompletedAgents: b.type === 'workflow' ? b.workflowCompletedAgents : undefined,
      workflowTotalAgents: b.type === 'workflow' ? b.workflowTotalAgents : undefined,
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

      for await (const evt of gen) {
        processEvent(evt);
        if (evt.event === 'thinking_delta' || evt.event === 'tool_start') {
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
        } else if (b.type === 'delegation') {
          msgBlocks.push({
            type: 'delegation',
            label: '协调专家',
            mode: b.mode,
            agents: b.agents,
            status: 'done',
            isError: b.isError,
          });
        } else if (b.type === 'plan') {
          msgBlocks.push({
            type: 'plan',
            label: b.planTitle || '执行计划',
            planId: b.planId,
            planTitle: b.planTitle,
            planStatus: b.planStatus,
            planDone: b.planDone,
            planTotal: b.planTotal,
            planSteps: b.planSteps,
            status: 'done',
            isError: b.isError,
          });
        } else if (b.type === 'workflow') {
          msgBlocks.push({
            type: 'workflow',
            label: b.workflowName || '工作流',
            workflowRunId: b.workflowRunId,
            workflowName: b.workflowName,
            workflowStatus: b.workflowStatus,
            workflowPhase: b.workflowPhase,
            workflowPhases: b.workflowPhases,
            workflowLog: b.workflowLog,
            workflowCompletedAgents: b.workflowCompletedAgents,
            workflowTotalAgents: b.workflowTotalAgents,
            status: 'done',
            isError: b.isError,
          });
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
