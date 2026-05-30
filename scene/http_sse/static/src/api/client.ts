import type { SSEEvent, SessionMeta } from './types';
import { API_BASE } from '../config';

/* ------------------------------------------------------------------ */
/* Retry helper                                                       */
/* ------------------------------------------------------------------ */

function isRetryableError(err: unknown): boolean {
  if (err instanceof Error) {
    if (err.name === 'AbortError' || err.name === 'DOMException') return false;
    if (err.message.startsWith('HTTP 4')) return false;
    return true;
  }
  return false;
}

async function withRetry<T>(fn: () => Promise<T>, retries = 2, delay = 1000): Promise<T> {
  let lastErr: unknown;
  for (let i = 0; i <= retries; i++) {
    try {
      return await fn();
    } catch (err: unknown) {
      lastErr = err;
      if (i === retries || !isRetryableError(err)) throw err;
      await new Promise((r) => setTimeout(r, delay * (i + 1)));
    }
  }
  throw lastErr;
}

export async function* streamChat(
  message: string,
  sessionId: string | null,
  authHeaders: Record<string, string>,
  signal?: AbortSignal,
  personaId?: string | null,
): AsyncGenerator<SSEEvent> {
  const url = new URL(`${API_BASE}/chat/stream`, window.location.origin);
  if (sessionId) url.searchParams.set('session_id', sessionId);
  if (personaId) url.searchParams.set('persona_id', personaId);

  const response = await withRetry(async () => {
    const res = await fetch(url.toString(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
      },
      body: JSON.stringify({ message }),
      signal,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    return res;
  }, 2, 1000);

  // lazy import to avoid circular dependency at module level
  const { parseSSEStream } = await import('./sse-parser');
  yield* parseSSEStream(response.body!.getReader());
}

export async function abortSession(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/abort?session_id=${encodeURIComponent(sessionId)}`, {
    method: 'POST',
  });
}

export async function fetchSessions(): Promise<SessionMeta[]> {
  const response = await fetch(`${API_BASE}/sessions`);
  if (!response.ok) {
    throw new Error(`Failed to fetch sessions: ${response.status}`);
  }
  const data = await response.json() as { sessions: SessionMeta[] };
  return data.sessions;
}

export async function deleteSession(sessionId: string): Promise<boolean> {
  const response = await fetch(`${API_BASE}/session?session_id=${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(`Failed to delete session: ${response.status}`);
  }
  const data = await response.json() as { success: boolean };
  return data.success;
}

export async function fetchSessionMessages(sessionId: string): Promise<Array<{ role: string; content: unknown; timestamp?: number }>> {
  const response = await fetch(`${API_BASE}/session?session_id=${encodeURIComponent(sessionId)}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch session messages: ${response.status}`);
  }
  const data = await response.json() as { success: boolean; messages?: Array<{ role: string; content: unknown; timestamp?: number }> };
  return data.messages ?? [];
}

export interface PersonaInfo {
  id: string;
  name: string;
  description: string;
  system_prompt?: string;
  enabled_tools?: string[] | null;
  knowledge_bases?: string[] | null;
}

export async function fetchPersonas(): Promise<PersonaInfo[]> {
  const response = await fetch(`${API_BASE}/personas`);
  if (!response.ok) {
    throw new Error(`Failed to fetch personas: ${response.status}`);
  }
  const data = await response.json() as { personas: PersonaInfo[] };
  return data.personas;
}

export interface SkillInfo {
  name: string;
  description: string;
}

export interface ToolInfo {
  name: string;
  description: string;
}

export interface Capabilities {
  skills: SkillInfo[];
  tools: ToolInfo[];
}

export async function uploadFile(file: File): Promise<{ filename: string; path: string; size: number }> {
  const form = new FormData();
  form.append('file', file);
  const response = await withRetry(async () => {
    const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res;
  }, 2, 1500);
  return response.json() as Promise<{ success: boolean; filename: string; path: string; size: number } & { success: boolean }>;
}

export async function importSkill(name: string, content: string): Promise<boolean> {
  const response = await fetch(`${API_BASE}/skills/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  });
  if (!response.ok) throw new Error(`Failed to import skill: ${response.status}`);
  return (await response.json() as { success: boolean }).success;
}

export async function fetchCapabilities(): Promise<Capabilities> {
  const response = await fetch(`${API_BASE}/capabilities`);
  if (!response.ok) {
    throw new Error(`Failed to fetch capabilities: ${response.status}`);
  }
  return response.json() as Promise<Capabilities>;
}

export interface ConnectorInfo {
  name: string;
  transport: string;
  status: string;
  type: string;
  tools: string[];
}

export interface AddConnectorPayload {
  name: string;
  transport: string;
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  type?: string;
}

export async function addConnector(payload: AddConnectorPayload): Promise<boolean> {
  const response = await fetch(`${API_BASE}/connectors`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`Failed to add connector: ${response.status}`);
  return (await response.json() as { success: boolean }).success;
}

export async function removeConnector(name: string): Promise<boolean> {
  const response = await fetch(`${API_BASE}/connectors?name=${encodeURIComponent(name)}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(`Failed to remove connector: ${response.status}`);
  return (await response.json() as { success: boolean }).success;
}

export async function savePersona(payload: PersonaInfo): Promise<boolean> {
  const response = await fetch(`${API_BASE}/personas`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`Failed to save persona: ${response.status}`);
  return (await response.json() as { success: boolean }).success;
}

export async function deletePersona(id: string): Promise<boolean> {
  const response = await fetch(`${API_BASE}/personas?id=${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(`Failed to delete persona: ${response.status}`);
  return (await response.json() as { success: boolean }).success;
}

export async function fetchConnectors(): Promise<ConnectorInfo[]> {
  const response = await fetch(`${API_BASE}/connectors`);
  if (!response.ok) {
    throw new Error(`Failed to fetch connectors: ${response.status}`);
  }
  const data = await response.json() as { connectors: ConnectorInfo[] };
  return data.connectors;
}

export interface KnowledgeDoc {
  name: string;
  original_name: string;
  created: number;
  chunk_count: number;
  tags: string[];
}

export async function setKnowledgeTags(name: string, tags: string[]): Promise<boolean> {
  const response = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(name)}/tags`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tags }),
  });
  if (!response.ok) return false;
  return (await response.json() as { success: boolean }).success;
}

export interface KnowledgeDocDetail extends KnowledgeDoc {
  content: string;
  chunks: Array<{ index: string; text: string; full_length: number }>;
}

export async function fetchKnowledgeDocs(): Promise<KnowledgeDoc[]> {
  const response = await fetch(`${API_BASE}/knowledge`);
  if (!response.ok) throw new Error(`Failed to fetch knowledge: ${response.status}`);
  const data = await response.json() as { docs: KnowledgeDoc[] };
  return data.docs;
}

export async function uploadKnowledgeFile(file: File): Promise<{ success: boolean; chunks: number }> {
  const form = new FormData();
  form.append('file', file);
  const response = await withRetry(async () => {
    const res = await fetch(`${API_BASE}/knowledge/upload`, {
      method: 'POST',
      body: form,
    });
    if (!res.ok) throw new Error(`Failed to upload: ${res.status}`);
    return res;
  }, 2, 1500);
  return response.json() as Promise<{ success: boolean; chunks: number }>;
}

export async function uploadKnowledgeDoc(name: string, content: string): Promise<{ success: boolean; chunks: number }> {
  const response = await withRetry(async () => {
    const res = await fetch(`${API_BASE}/knowledge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, content }),
    });
    if (!res.ok) throw new Error(`Failed to upload: ${res.status}`);
    return res;
  }, 2, 1000);
  return response.json() as Promise<{ success: boolean; chunks: number }>;
}

export async function fetchKnowledgeDoc(name: string): Promise<KnowledgeDocDetail | null> {
  const response = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(name)}`);
  if (!response.ok) return null;
  const data = await response.json() as { success: boolean; doc?: KnowledgeDocDetail };
  return data.doc || null;
}

export async function deleteKnowledgeDoc(name: string): Promise<boolean> {
  const response = await fetch(`${API_BASE}/knowledge?name=${encodeURIComponent(name)}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(`Failed to delete: ${response.status}`);
  return (await response.json() as { success: boolean }).success;
}

export async function submitHumanInput(
  sessionId: string,
  toolCallId: string,
  values: Record<string, unknown>,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/human-input?session_id=${encodeURIComponent(sessionId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool_call_id: toolCallId, values }),
    },
  );
  if (!response.ok) {
    throw new Error(`Human input failed: ${response.status}`);
  }
}

// ---- Channel management ----

export interface ChannelInfo {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
  app_id: string;
  app_secret: string;
}

export async function fetchChannels(): Promise<ChannelInfo[]> {
  const resp = await fetch(`${API_BASE}/channels`);
  if (!resp.ok) throw new Error(`Fetch channels failed: ${resp.status}`);
  const data = await resp.json() as { channels: ChannelInfo[] };
  return data.channels;
}

export async function saveChannel(ch: ChannelInfo): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/channels`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ch),
  });
  if (!resp.ok) throw new Error(`Save channel failed: ${resp.status}`);
  return (await resp.json() as { success: boolean }).success;
}

export async function deleteChannel(channelId: string): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/channels/${encodeURIComponent(channelId)}`, {
    method: 'DELETE',
  });
  if (!resp.ok) throw new Error(`Delete channel failed: ${resp.status}`);
  return (await resp.json() as { success: boolean }).success;
}
