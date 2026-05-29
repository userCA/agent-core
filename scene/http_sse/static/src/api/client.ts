import type { SSEEvent, SessionMeta } from './types';
import { API_BASE } from '../config';

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

  const response = await fetch(url.toString(), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
    },
    body: JSON.stringify({ message }),
    signal,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`HTTP ${response.status}: ${text || response.statusText}`);
  }

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

export interface Capabilities {
  skills: SkillInfo[];
  tools: string[];
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
