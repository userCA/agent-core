/**
 * API 客户端 — 移植自 scene/h5/static/src/api/client.ts
 *
 * 小程序适配要点：
 * - 使用 uni.request 替代 fetch
 * - 流式聊天使用 uni.request + enableChunked: true
 * - 鉴权 header 统一注入
 */

import { API_BASE } from './config.js';
import { createSSEParser } from './sse-parser.js';

/* ------------------------------------------------------------------ */
/* 通用请求封装                                                         */
/* ------------------------------------------------------------------ */

/**
 * 封装 uni.request 为 Promise
 * @param {string} url - 相对路径（会自动拼接 API_BASE）
 * @param {object} options
 * @param {string} options.method - HTTP 方法
 * @param {object} [options.header] - 请求头
 * @param {object} [options.data] - 请求体
 * @returns {Promise<{statusCode: number, data: any}>}
 */
function request(url, options = {}) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: url.startsWith('http') ? url : `${API_BASE}${url}`,
      method: options.method || 'GET',
      header: {
        'Content-Type': 'application/json',
        ...(options.header || {}),
      },
      data: options.data,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res);
        } else {
          const err = new Error(`HTTP ${res.statusCode}`);
          err.statusCode = res.statusCode;
          err.data = res.data;
          reject(err);
        }
      },
      fail: (err) => {
        reject(new Error(err.errMsg || '网络请求失败'));
      },
    });
  });
}

/* ------------------------------------------------------------------ */
/* 流式聊天 — POST /chat/stream (chunked SSE)                        */
/* ------------------------------------------------------------------ */

/**
 * 发起流式聊天请求
 *
 * 使用 uni.request 的 enableChunked 能力接收 SSE 分片。
 * 通过回调方式传递事件，不使用 AsyncGenerator（小程序环境不支持）。
 *
 * @param {object} params
 * @param {string} params.message - 用户消息文本
 * @param {string|null} params.sessionId - 会话 ID
 * @param {object} params.authHeaders - 鉴权头
 * @param {string|null} [params.personaId] - Persona ID
 * @param {string|null} [params.providerId] - 模型 Provider
 * @param {string|null} [params.modelId] - 模型 ID
 * @param {Array} [params.content] - 多模态内容块
 * @param {function} params.onFrame - SSE 帧回调 ({ sseEvent, data }) => void
 * @param {function} params.onDone - 流结束回调 () => void
 * @param {function} params.onError - 错误回调 (error) => void
 * @returns {{ abort: function }} 包含 abort 方法的控制对象
 */
export function streamChat(params) {
  const {
    message,
    sessionId,
    authHeaders,
    personaId,
    providerId,
    modelId,
    content,
    onFrame,
    onDone,
    onError,
  } = params;

  // 构造 URL（含查询参数）
  let url = `${API_BASE}/chat/stream`;
  const queryParts = [];
  if (sessionId) queryParts.push(`session_id=${encodeURIComponent(sessionId)}`);
  if (personaId) queryParts.push(`persona_id=${encodeURIComponent(personaId)}`);
  if (queryParts.length > 0) url += '?' + queryParts.join('&');

  // 构造请求体
  const body = { message, provider: providerId || null, model: modelId || null };
  if (content && content.length > 0) {
    body.content = content;
  }

  console.log('[streamChat] POST', url, 'body=', JSON.stringify(body).slice(0, 200));

  // 创建 SSE 解析器
  let doneCalled = false;
  const parser = createSSEParser(
    (frame) => {
      if (!doneCalled && onFrame) onFrame(frame);
    },
    () => {
      if (!doneCalled) {
        doneCalled = true;
        if (onDone) onDone();
      }
    },
    (err) => {
      if (!doneCalled && onError) onError(err);
    },
  );

  // 发起 chunked 请求
  // uni.request 在微信小程序平台编译时支持 enableChunked
  const requestTask = uni.request({
    url,
    method: 'POST',
    enableChunked: true,
    header: {
      'Content-Type': 'application/json',
      ...(authHeaders || {}),
    },
    data: body,
    // 请求成功（非流式场景的兜底）
    success: (res) => {
      console.log('[streamChat] request success, statusCode:', res.statusCode);
      // 如果是非 chunked 的完整响应（降级场景）
      if (typeof res.data === 'string' && res.data.includes('event:')) {
        // 整段 SSE 文本，一次性解析
        const encoder = new TextEncoder();
        parser.feed(encoder.encode(res.data).buffer);
      }
      parser.flush();
      if (!doneCalled) {
        doneCalled = true;
        if (onDone) onDone();
      }
    },
    fail: (err) => {
      console.error('[streamChat] request fail:', err);
      if (!doneCalled) {
        doneCalled = true;
        if (onError) onError(new Error(err.errMsg || '请求失败'));
      }
    },
  });

  // 监听分片数据
  if (requestTask && requestTask.onChunkReceived) {
    requestTask.onChunkReceived((res) => {
      // res.data 是 ArrayBuffer
      if (res.data) {
        parser.feed(res.data);
      }
    });
  } else {
    console.warn('[streamChat] onChunkReceived 不可用，流式可能不工作');
  }

  return {
    abort() {
      if (requestTask) {
        requestTask.abort();
      }
    },
  };
}

/* ------------------------------------------------------------------ */
/* 中止会话 — POST /abort                                              */
/* ------------------------------------------------------------------ */

export async function abortSession(sessionId) {
  try {
    await request(`/abort?session_id=${encodeURIComponent(sessionId)}`, {
      method: 'POST',
    });
  } catch (e) {
    console.warn('[abortSession] failed:', e);
  }
}

/* ------------------------------------------------------------------ */
/* 会话列表 — GET /sessions                                            */
/* ------------------------------------------------------------------ */

export async function fetchSessions() {
  const res = await request('/sessions');
  return res.data.sessions || [];
}

/* ------------------------------------------------------------------ */
/* 会话消息 — GET /session                                             */
/* ------------------------------------------------------------------ */

export async function fetchSessionMessages(sessionId) {
  const res = await request(`/session?session_id=${encodeURIComponent(sessionId)}`);
  return res.data.messages || [];
}

/* ------------------------------------------------------------------ */
/* 删除会话 — DELETE /session                                          */
/* ------------------------------------------------------------------ */

export async function deleteSession(sessionId) {
  const res = await request(`/session?session_id=${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });
  return res.data.success || false;
}

/* ------------------------------------------------------------------ */
/* HITL 提交 — POST /human-input                                       */
/* ------------------------------------------------------------------ */

export async function submitHumanInput(sessionId, toolCallId, values) {
  await request(`/human-input?session_id=${encodeURIComponent(sessionId)}`, {
    method: 'POST',
    data: { tool_call_id: toolCallId, values },
  });
}

/* ------------------------------------------------------------------ */
/* 模型列表 — GET /models                                              */
/* ------------------------------------------------------------------ */

export async function fetchModels() {
  const res = await request('/models');
  return res.data;
}

/* ------------------------------------------------------------------ */
/* 文件上传 — POST /upload                                             */
/* ------------------------------------------------------------------ */

/**
 * 上传图片文件
 * @param {string} filePath - 本地临时文件路径
 * @param {object} authHeaders - 鉴权头
 * @returns {Promise<{url: string}>} 上传后的 URL
 */
export async function uploadFile(filePath, authHeaders) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: `${API_BASE}/upload`,
      filePath,
      name: 'file',
      header: authHeaders || {},
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            const data = JSON.parse(res.data);
            resolve({ url: data.url || data.path || '' });
          } catch (e) {
            resolve({ url: res.data });
          }
        } else {
          reject(new Error(`Upload failed: HTTP ${res.statusCode}`));
        }
      },
      fail: (err) => {
        reject(new Error(err.errMsg || '上传失败'));
      },
    });
  });
}

/* ------------------------------------------------------------------ */
/* 伴侣 — GET /api/companion/{uid} + POST /hatch                       */
/* ------------------------------------------------------------------ */

/**
 * 获取伴侣骨骼数据
 * @param {string} uid
 * @returns {Promise<object>} CompanionBones
 */
export async function fetchCompanion(uid) {
  const res = await request(`/api/companion/${encodeURIComponent(uid)}`);
  return res.data;
}

/**
 * 孵化伴侣（首次生成名字和个性）
 * @param {string} uid
 * @returns {Promise<object>} CompanionBones
 */
export async function hatchCompanion(uid) {
  const res = await request(`/api/companion/${encodeURIComponent(uid)}/hatch`, {
    method: 'POST',
  });
  return res.data;
}

/* ------------------------------------------------------------------ */
/* P2 — Skills / Persona / Evolution                                   */
/* ------------------------------------------------------------------ */

/**
 * 获取可用技能与工具列表
 * @returns {Promise<{skills: Array<{name: string, description: string}>, tools: Array<{name: string, description: string}>}>}
 */
export async function fetchCapabilities() {
  const res = await request('/capabilities');
  return res.data;
}

/**
 * 导入技能（Markdown 内容）
 * @param {string} name
 * @param {string} content
 * @returns {Promise<boolean>}
 */
export async function importSkill(name, content) {
  const res = await request('/skills/import', {
    method: 'POST',
    data: { name, content },
  });
  return res.data.success || false;
}

/**
 * 获取 Persona 列表
 * @returns {Promise<Array<{id: string, name: string, description: string}>>}
 */
export async function fetchPersonas() {
  const res = await request('/personas');
  return res.data.personas || [];
}

/**
 * 获取进化摘要
 * @returns {Promise<object>} EvolutionSummary
 */
export async function fetchEvolutionSummary() {
  const res = await request('/skills/evolution/summary');
  return res.data;
}

/**
 * 分析技能进化
 * @param {string} skillName
 * @param {number} [minTraces=10]
 * @returns {Promise<object>} EvolutionAnalyzeResult
 */
export async function analyzeSkillEvolution(skillName, minTraces = 10) {
  const res = await request('/skills/evolution/analyze', {
    method: 'POST',
    data: { skill_name: skillName, min_traces: minTraces },
  });
  return res.data;
}

/**
 * 获取技能进化提议
 * @param {string} skillName
 * @returns {Promise<Array>}
 */
export async function fetchEvolutionProposals(skillName) {
  const res = await request(`/skills/evolution/proposals/${encodeURIComponent(skillName)}`);
  return res.data.proposals || [];
}

/**
 * 接受进化提议
 * @param {string} proposalId
 * @param {string} skillName
 * @returns {Promise<{success: boolean}>}
 */
export async function acceptEvolutionProposal(proposalId, skillName) {
  const res = await request(`/skills/evolution/proposals/${encodeURIComponent(proposalId)}/accept`, {
    method: 'POST',
    data: { skill_name: skillName },
  });
  return res.data;
}

/**
 * 拒绝进化提议
 * @param {string} proposalId
 * @param {string} skillName
 * @param {string} [reason]
 * @returns {Promise<{success: boolean}>}
 */
export async function rejectEvolutionProposal(proposalId, skillName, reason) {
  const res = await request(`/skills/evolution/proposals/${encodeURIComponent(proposalId)}/reject`, {
    method: 'POST',
    data: { skill_name: skillName, reason: reason || null },
  });
  return res.data;
}

/**
 * 获取进化审计记录
 * @param {string} [skillName]
 * @param {number} [limit=50]
 * @returns {Promise<{entries: Array, total: number}>}
 */
export async function fetchEvolutionAudit(skillName, limit = 50) {
  let url = `/skills/evolution/audit?limit=${limit}`;
  if (skillName) url += `&skill_name=${encodeURIComponent(skillName)}`;
  const res = await request(url);
  return res.data;
}
