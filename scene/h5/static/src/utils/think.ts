export interface ExtractedThink {
  content: string;
  startIndex: number;
  endIndex: number;
  text: string;
}

/** Stack-based extraction that correctly handles nested <think> blocks. */
export function extractThinkSteps(text: string, alreadySeen: Set<string>): ExtractedThink[] {
  const results: ExtractedThink[] = [];
  let pos = 0;

  while (true) {
    const openIdx = text.indexOf('<think>', pos);
    if (openIdx === -1) break;

    let depth = 1;
    let searchFrom = openIdx + '<think>'.length;
    let closeIdx = -1;

    while (depth > 0) {
      const nextOpen = text.indexOf('<think>', searchFrom);
      const nextClose = text.indexOf('</think>', searchFrom);

      if (nextClose === -1) break;

      if (nextOpen !== -1 && nextOpen < nextClose) {
        depth++;
        searchFrom = nextOpen + '<think>'.length;
      } else {
        depth--;
        closeIdx = nextClose;
        searchFrom = nextClose + '</think>'.length;
      }
    }

    if (closeIdx === -1) break;

    const content = text.slice(openIdx + '<think>'.length, closeIdx).trim();
    if (content && !alreadySeen.has(content)) {
      alreadySeen.add(content);
      results.push({
        content,
        startIndex: openIdx,
        endIndex: closeIdx + '</think>'.length,
        text: text.slice(openIdx, closeIdx + '</think>'.length),
      });
    }

    pos = closeIdx + '</think>'.length;
  }

  return results;
}

export function stripThinkTags(text: string): string {
  return getDisplayableText(text).trim();
}

/**
 * Strip think blocks, handling three streaming states:
 *   1. Complete (nested-safe): <think>...</think>  → removed
 *   2. Unterminated: <think>... (no close) → trim from <think> onward
 *   3. Partial opening: <think (no > yet)   → trim from <think onward
 */
export function getDisplayableText(text: string): string {
  let result = text;
  let i = 0;

  while (true) {
    const openIdx = result.indexOf('<think>', i);
    if (openIdx === -1) break;

    // Stack-based matching for nested tags
    let depth = 1;
    let pos = openIdx + '<think>'.length;
    let closeIdx = -1;

    while (depth > 0 && pos < result.length) {
      const nextOpen = result.indexOf('<think>', pos);
      const nextClose = result.indexOf('</think>', pos);

      if (nextClose === -1) {
        return result.slice(0, openIdx);
      }

      if (nextOpen !== -1 && nextOpen < nextClose) {
        depth++;
        pos = nextOpen + '<think>'.length;
      } else {
        depth--;
        closeIdx = nextClose;
        pos = nextClose + '</think>'.length;
      }
    }

    if (closeIdx === -1) {
      return result.slice(0, openIdx);
    }

    result = result.slice(0, openIdx) + result.slice(closeIdx + '</think>'.length);
    i = openIdx;
  }

  // Trim from partial <think (missing >) — streaming artifact
  const partial = result.indexOf('<think');
  if (partial !== -1 && !result.startsWith('<think>', partial)) {
    result = result.slice(0, partial);
  }

  return result;
}

/**
 * Extract partial content from the last unclosed <think> block.
 * Strips all complete blocks first, then returns trailing unclosed content
 * for streaming display. Returns null when all blocks are properly closed.
 */
export function getStreamingThinkContent(text: string): string | null {
  let cleaned = text;

  // Strip all complete <think>...</think> blocks (stack-based for nesting)
  while (true) {
    const openIdx = cleaned.indexOf('<think>');
    if (openIdx === -1) break;

    let depth = 1;
    let pos = openIdx + '<think>'.length;
    let closeIdx = -1;

    while (depth > 0 && pos < cleaned.length) {
      const nextOpen = cleaned.indexOf('<think>', pos);
      const nextClose = cleaned.indexOf('</think>', pos);

      if (nextClose === -1) {
        // Unclosed — return content after opening tag
        return cleaned.slice(openIdx + '<think>'.length);
      }

      if (nextOpen !== -1 && nextOpen < nextClose) {
        depth++;
        pos = nextOpen + '<think>'.length;
      } else {
        depth--;
        closeIdx = nextClose;
        pos = nextClose + '</think>'.length;
      }
    }

    if (closeIdx === -1) {
      return cleaned.slice(openIdx + '<think>'.length);
    }

    // Strip this complete block and continue
    cleaned = cleaned.slice(0, openIdx) + cleaned.slice(closeIdx + '</think>'.length);
  }

  return null;
}
