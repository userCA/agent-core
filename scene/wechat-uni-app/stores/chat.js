/**
 * Chat Store — 移植自 scene/h5/static/src/stores/chat-store.ts
 *
 * 使用 Vue 3 reactive 替代 Zustand。
 * 管理消息列表、流式状态、内容块、HITL 请求等。
 */

import { reactive } from 'vue';
import { streamChat, abortSession, submitHumanInput, fetchSessionMessages } from '../api/client.js';
import { sessionStore } from './session.js';

/* ------------------------------------------------------------------ */
/* 数据类型（JSDoc 注释，不使用 TS）                                     */
/* ------------------------------------------------------------------ */

/**
 * @typedef {Object} MessageBlock
 * @property {'text'|'think'|'tool'|'widget'|'video'|'image'|'skill'|'delegation'|'plan'} type
 * @property {string} [text]
 * @property {string} [label]
 * @property {string} [detail]
 * @property {boolean} [isError]
 * @property {'running'|'done'} [status]
 * @property {'intermediate'|'final'} [turnPhase]
 */

/**
 * @typedef {Object} ChatMessage
 * @property {string} id
 * @property {'user'|'assistant'|'error'} role
 * @property {string} content
 * @property {MessageBlock[]} [blocks]
 * @property {MessageBlock[]} [intermediateBlocks]
 * @property {number} timestamp
 */

/**
 * @typedef {Object} HitlRequest
 * @property {string} toolCallId
 * @property {string} prompt
 * @property {Object} inputSchema
 */

/* ------------------------------------------------------------------ */
/* 辅助函数                                                             */
/* ------------------------------------------------------------------ */

function generateId() {
  const t = Date.now().toString(36);
  const r = Math.random().toString(36).slice(2, 6);
  return `user-${t}-${r}`;
}

/* ------------------------------------------------------------------ */
/* Store 定义                                                           */
/* ------------------------------------------------------------------ */

export const chatStore = reactive({
  /** @type {ChatMessage[]} */
  messages: [],
  streamingMessageId: null,
  isStreaming: false,
  /** @type {string[]} */
  pendingQueue: [],
  currentText: '',
  thinkingText: '',
  /** @type {MessageBlock[]} */
  streamBlocks: [],
  usage: null,
  /** @type {HitlRequest|null} */
  hitlRequest: null,
  welcomeVisible: true,

  // ---- Actions ----

  addMessage(msg) {
    this.messages = [...this.messages, msg];
  },

  setStreaming(v) {
    this.isStreaming = v;
  },

  setStreamingMessageId(id) {
    this.streamingMessageId = id;
  },

  appendText(text) {
    this.currentText += text;
  },

  appendThinking(text) {
    this.thinkingText += text;
  },

  setUsage(u) {
    this.usage = u;
  },

  setStreamBlocks(blocks) {
    this.streamBlocks = blocks;
  },

  setHitlRequest(h) {
    this.hitlRequest = h;
  },

  enqueuePending(text) {
    this.pendingQueue = [...this.pendingQueue, text];
  },

  dequeuePending() {
    if (this.pendingQueue.length === 0) return undefined;
    const [head, ...rest] = this.pendingQueue;
    this.pendingQueue = rest;
    return head;
  },

  resetSteps() {
    this.streamBlocks = [];
    this.currentText = '';
    this.thinkingText = '';
    this.usage = null;
    this.hitlRequest = null;
  },

  reset() {
    this.messages = [];
    this.streamingMessageId = null;
    this.isStreaming = false;
    this.pendingQueue = [];
    this.currentText = '';
    this.thinkingText = '';
    this.usage = null;
    this.hitlRequest = null;
  },

  setWelcomeVisible(v) {
    this.welcomeVisible = v;
  },

  /**
   * 从后端加载指定会话的历史消息
   * @param {string} sessionId
   */
  async loadMessages(sessionId) {
    try {
      const rawMessages = await fetchSessionMessages(sessionId);
      this.messages = rawMessages.map((m, idx) => ({
        id: m.id || `hist-${idx}-${Date.now()}`,
        role: m.role || 'assistant',
        content: m.content || '',
        blocks: m.blocks || undefined,
        intermediateBlocks: m.intermediateBlocks || undefined,
        timestamp: m.timestamp || Date.now(),
      }));
      this.setWelcomeVisible(this.messages.length === 0);
    } catch (e) {
      console.warn('[chat] loadMessages failed:', e);
      this.messages = [];
      this.setWelcomeVisible(true);
    }
  },
});

/* ------------------------------------------------------------------ */
/* SSE 事件处理 + 流式发送逻辑                                           */
/* ------------------------------------------------------------------ */

// 内部状态（不需要响应式）
let _abortController = null;
let _blocks = []; // 内部 block 追踪
let _errorShown = false;
let _turnStartIdx = 0;
let _currentTurnPhase = 'intermediate';
let _inThinkTag = false; // 追踪是否在 <think> 标签内

/**
 * 处理单个 SSE 事件帧 — 移植自 useSSE.ts processEvent
 * @param {{ sseEvent: string, data: object }} frame
 */
function processEvent(frame) {
  const evt = frame.data;
  const blocks = _blocks;

  const type = evt.type;
  const actionType = evt.actionType;

  // ---- 消息生命周期 ----
  if (type === 'message.start') {
    sessionStore.setSessionId(evt.sessionId);
    _turnStartIdx = blocks.length;
    _currentTurnPhase = 'intermediate';
  } else if (type === 'message.end') {
    chatStore.setUsage(evt.usage);
    const phase = evt.stopReason === 'end_turn' ? 'final' : 'intermediate';
    for (let i = _turnStartIdx; i < blocks.length; i++) {
      blocks[i].turnPhase = phase;
    }
    _currentTurnPhase = phase;
    if (phase === 'final') {
      let turnText = '';
      for (let i = _turnStartIdx; i < blocks.length; i++) {
        if (blocks[i].type === 'text') turnText += blocks[i].content || '';
      }
      if (turnText) chatStore.currentText = turnText;
    } else {
      chatStore.currentText = '';
    }
    if (evt.stopReason === 'error' && !_errorShown) {
      _errorShown = true;
      const errMsg = '服务暂时不可用，请稍后重试';
      uni.showToast({ title: errMsg, icon: 'none' });
      chatStore.addMessage({
        id: `err-${Date.now()}`, role: 'error', content: errMsg, timestamp: Date.now(),
      });
    }
    // 同步 blocks 到 store
    syncBlocks();
  } else if (type === 'message.error') {
    const rawMsg = (evt.error && evt.error.message) || (evt.error && evt.error.type) || '未知错误';
    let friendly = rawMsg;
    if (rawMsg.includes('rate_limit') || rawMsg.includes('429')) {
      friendly = '请求过于频繁，请稍后再试';
    } else if (rawMsg.includes('500')) {
      friendly = '服务暂时不可用，请稍后重试';
    } else if (rawMsg.includes('timeout')) {
      friendly = '请求超时，请检查网络后重试';
    } else if (rawMsg.includes('auth') || rawMsg.includes('Unauthorized')) {
      friendly = '认证失败，请检查 API 设置';
    }
    if (!_errorShown) {
      _errorShown = true;
      chatStore.addMessage({
        id: `err-${Date.now()}`, role: 'error', content: friendly, timestamp: Date.now(),
      });
    }
  } else if (type === 'heart') {
    // no-op
  } else if (type === 'state.snapshot' || type === 'state.delta') {
    // Future: sync agent state
  }
  // ---- Action 事件 ----
  else if (actionType) {
    const ae = evt;
    switch (actionType) {
      case 'tool_call.started': {
        if (ae.name === 'delegate_task' || ae.name === 'manage_plan') break;
        blocks.push({
          type: 'tool',
          content: JSON.stringify(ae.arguments),
          toolName: ae.name || ae.toolCallId || 'tool',
          toolCallId: ae.toolCallId,
          status: 'running',
        });
        break;
      }
      case 'tool_call.completed': {
        if (ae.name === 'delegate_task' || ae.name === 'manage_plan') break;
        const b = blocks.find((blk) => blk.toolCallId === ae.toolCallId && blk.type === 'tool');
        if (b) {
          b.content = (ae.result && ae.result.output) || '';
          b.status = 'done';
          b.isError = ae.result && ae.result.isError;
        }
        break;
      }
      case 'tool_call.progress':
        break;
      case 'skill.started': {
        blocks.push({
          type: 'skill',
          content: ae.skillName || ae.skillId,
          toolName: ae.skillName || ae.skillId,
          status: 'running',
        });
        break;
      }
      case 'skill.completed': {
        const sb = [...blocks].reverse().find(
          (blk) => blk.type === 'skill' && blk.toolName === ae.skillId && blk.status === 'running',
        );
        if (sb) sb.status = 'done';
        break;
      }
      case 'human_input.required': {
        chatStore.setHitlRequest({
          toolCallId: ae.toolCallId,
          prompt: ae.prompt,
          inputSchema: ae.inputSchema,
        });
        break;
      }
      case 'human_input.submitted': {
        chatStore.setHitlRequest(null);
        break;
      }
      case 'delegation.update':
      case 'plan.update':
        // P0 暂不实现 delegation/plan 可视化
        break;
    }
    syncBlocks();
  }
  // ---- 内容块（三阶段: start → delta → done）----
  else if (evt.phase !== undefined) {
    const cb = evt;
    if (cb.type === 'text') {
      if (cb.phase === 'start') {
        const prev = blocks[blocks.length - 1];
        if (prev && prev.type === 'think' && prev.status === 'running') {
          prev.status = 'done';
        }
        blocks.push({ type: 'text', content: '' });
      } else if (cb.phase === 'delta') {
        const prev = blocks[blocks.length - 1];
        if (prev && prev.type === 'text') {
          prev.content = (prev.content || '') + cb.content;
        } else {
          blocks.push({ type: 'text', content: cb.content });
        }
        // 实时追加文本到流式气泡（跳过  内文本）
        if (!_inThinkTag) {
          chatStore.appendText(cb.content);
        }
      }
      // phase=done: no-op
    } else if (cb.type === 'thinking') {
      if (cb.phase === 'start') {
        blocks.push({ type: 'think', content: '', status: 'running' });
        _inThinkTag = true;
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
        _inThinkTag = false;
      }
      syncBlocks();
    } else if (cb.phase === 'done') {
      // 非文本内容（image/video/audio/file）
      if (cb.type === 'image') {
        blocks.push({
          type: 'image', content: cb.content || '',
          imageUrl: cb.content || '', status: 'done',
        });
      } else if (cb.type === 'video') {
        blocks.push({
          type: 'video', content: cb.content || '',
          videoUrl: cb.content || '', status: 'done',
        });
      }
      syncBlocks();
    }
  }

  // Tag untagged blocks
  for (let i = 0; i < blocks.length; i++) {
    if (!blocks[i].turnPhase) blocks[i].turnPhase = _currentTurnPhase;
  }
}

/**
 * 同步内部 blocks 到 store（转为 MessageBlock 格式）
 */
function syncBlocks() {
  chatStore.setStreamBlocks(
    _blocks.map((b) => ({
      type: b.type,
      text: b.type === 'text' ? b.content : undefined,
      label: b.type === 'tool' ? b.toolName
        : b.type === 'skill' ? b.toolName
        : undefined,
      detail: b.content,
      isError: b.isError,
      status: b.status,
      turnPhase: b.turnPhase,
      toolName: b.toolName,
      toolCallId: b.toolCallId,
      imageUrl: b.imageUrl,
      videoUrl: b.videoUrl,
    })),
  );
}

/**
 * 发送消息并启动流式接收
 *
 * @param {string} text - 用户消息
 */
export function sendMessage(text) {
  if (!text.trim()) return;

  chatStore.setWelcomeVisible(false);

  // 添加用户消息
  chatStore.addMessage({
    id: `user-${Date.now()}`,
    role: 'user',
    content: text,
    timestamp: Date.now(),
  });

  // 如果正在流式中，加入队列
  if (chatStore.isStreaming) {
    chatStore.enqueuePending(text);
    return;
  }

  _runStream(text);
}

/**
 * 内部：执行流式请求
 */
function _runStream(text) {
  chatStore.setStreaming(true);
  chatStore.resetSteps();
  _blocks = [];
  _errorShown = false;
  _turnStartIdx = 0;
  _currentTurnPhase = 'intermediate';
  _inThinkTag = false;

  const assistantId = `asst-${Date.now()}`;
  chatStore.setStreamingMessageId(assistantId);

  const authHeaders = sessionStore.buildAuthHeaders();
  const personaId = sessionStore.personaId;

  const controller = streamChat({
    message: text,
    sessionId: sessionStore.sessionId,
    authHeaders,
    personaId,
    onFrame(frame) {
      processEvent(frame);
    },
    onDone() {
      _finishStream(assistantId);
    },
    onError(err) {
      console.error('[stream] error:', err);
      if (!_errorShown) {
        _errorShown = true;
        const msg = err.message || '流式连接失败';
        uni.showToast({ title: msg, icon: 'none' });
        chatStore.addMessage({
          id: `err-${Date.now()}`, role: 'error', content: msg, timestamp: Date.now(),
        });
      }
      _finishStream(assistantId);
    },
  });

  _abortController = controller;
}

/**
 * 内部：流式结束，整理 blocks 并生成最终消息
 */
function _finishStream(assistantId) {
  // 标记所有 running blocks 为 done
  for (const b of _blocks) {
    if (b.status === 'running') b.status = 'done';
  }

  // 构建最终消息
  const contentParts = [];
  const intermediateBlocks = [];
  const finalBlocks = [];

  for (const b of _blocks) {
    const c = b.content || '';
    let mb = null;
    if (b.type === 'text') {
      contentParts.push(c);
      mb = { type: 'text', text: c, turnPhase: b.turnPhase };
    } else if (b.type === 'think') {
      mb = { type: 'think', detail: c, turnPhase: b.turnPhase };
    } else if (b.type === 'tool') {
      mb = {
        type: 'tool', label: b.toolName, detail: c,
        isError: b.isError, status: 'done', turnPhase: b.turnPhase,
      };
    } else if (b.type === 'skill') {
      mb = {
        type: 'skill', label: b.toolName, detail: c,
        status: 'done', turnPhase: b.turnPhase,
      };
    } else if (b.type === 'image') {
      mb = { type: 'image', imageUrl: b.imageUrl, detail: b.imageUrl, turnPhase: b.turnPhase };
    } else if (b.type === 'video') {
      mb = { type: 'video', videoUrl: b.videoUrl, detail: b.videoUrl, turnPhase: b.turnPhase };
    }

    if (mb) {
      if (b.turnPhase === 'intermediate') {
        intermediateBlocks.push(mb);
      } else {
        finalBlocks.push(mb);
      }
    }
  }

  let content = contentParts.join('').trim();
  if (!content) {
    const hasMedia = finalBlocks.some((b) => b.type === 'image' || b.type === 'video');
    content = hasMedia ? '已生成媒体内容' : '(empty)';
  }

  const hasError = _blocks.length === 0 && content === '(empty)';
  if (!hasError) {
    const allBlocks = [...intermediateBlocks, ...finalBlocks];
    chatStore.addMessage({
      id: assistantId,
      role: 'assistant',
      content,
      blocks: allBlocks.length > 0 ? allBlocks : undefined,
      intermediateBlocks: intermediateBlocks.length > 0 ? intermediateBlocks : undefined,
      timestamp: Date.now(),
    });
  }

  // 清理
  chatStore.setStreamingMessageId(null);
  chatStore.setStreaming(false);
  chatStore.currentText = '';
  chatStore.resetSteps();
  _abortController = null;

  // 检查待发队列
  const pending = chatStore.dequeuePending();
  if (pending) {
    setTimeout(() => _runStream(pending), 300);
  }
}

/**
 * 中止当前流式传输
 */
export async function abortStream() {
  if (_abortController) {
    _abortController.abort();
    _abortController = null;
  }
  const sid = sessionStore.sessionId;
  if (sid) {
    try {
      await abortSession(sid);
    } catch (e) {
      // best-effort
    }
  }
}

/**
 * 提交 HITL 人工输入
 * @param {string} toolCallId
 * @param {object} values - 表单值
 */
export async function submitHitl(toolCallId, values) {
  const sid = sessionStore.sessionId;
  if (!sid) return;
  try {
    await submitHumanInput(sid, toolCallId, values);
    chatStore.setHitlRequest(null);
  } catch (e) {
    console.error('[hitl] submit failed:', e);
    uni.showToast({ title: '提交失败，请重试', icon: 'none' });
    throw e;
  }
}
