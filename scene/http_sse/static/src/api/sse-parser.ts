import type { SSEEvent } from './types';

/**
 * Parse SSE text stream into SSEEvent objects.
 * Mirrors the legacy JS logic: split on \n\n → extract data: prefix → parse JSON.
 */
export async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>
): AsyncGenerator<SSEEvent> {
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';

    for (const part of parts) {
      const lines = part.split('\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const json = line.slice(6);
          if (json) {
            try {
              yield JSON.parse(json) as SSEEvent;
            } catch {
              // ignore malformed JSON
            }
          }
        }
      }
    }
  }
}
