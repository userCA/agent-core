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
  tools: string[];
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
