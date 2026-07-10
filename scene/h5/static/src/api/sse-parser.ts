import type { SSEEvent } from './types';

/**
 * Parsed SSE frame: the SSE channel name + parsed JSON data.
 */
export interface SSEFrame {
  /** SSE ``event:`` channel (e.g. "heart", "message", "content", "action", "state", "companion") */
  sseEvent: string;
  /** Parsed JSON payload */
  data: SSEEvent;
}

/**
 * Parse SSE text stream into {@link SSEFrame} objects.
 *
 * Handles both ``event:`` channel lines and ``data:`` payload lines.
 * Terminates on ``data: [DONE]``.
 */
export async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>
): AsyncGenerator<SSEFrame> {
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      // Process any remaining data in buffer before exiting
      if (buffer.trim()) {
        let channel = '';
        const lines = buffer.split('\n');
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            channel = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            const raw = line.slice(6);
            if (raw === '[DONE]') return;
            if (raw) {
              try {
                const data = JSON.parse(raw) as SSEEvent;
                yield { sseEvent: channel || 'message', data };
              } catch {
                // ignore malformed JSON
              }
            }
          }
        }
      }
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';

    for (const part of parts) {
      let channel = '';  // current event: channel
      const lines = part.split('\n');
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          channel = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          const raw = line.slice(6);

          // Termination signal
          if (raw === '[DONE]') return;

          if (raw) {
            try {
              const data = JSON.parse(raw) as SSEEvent;
              yield { sseEvent: channel || 'message', data };
            } catch {
              // ignore malformed JSON
            }
          }
        }
      }
    }
  }
}
