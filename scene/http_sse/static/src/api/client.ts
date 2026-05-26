import type { SSEEvent } from './types';
import { API_BASE } from '../config';

export async function* streamChat(
  message: string,
  sessionId: string | null,
  authHeaders: Record<string, string>,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const url = new URL(`${API_BASE}/chat/stream`, window.location.origin);
  if (sessionId) url.searchParams.set('session_id', sessionId);

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
