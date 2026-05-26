const THINK_RE = /<think>([\s\S]*?)<\/think>/g;

export interface ExtractedThink {
  content: string;
  startIndex: number;
  endIndex: number;
  text: string;
}

export function extractThinkSteps(text: string, alreadySeen: Set<string>): ExtractedThink[] {
  const results: ExtractedThink[] = [];
  let match: RegExpExecArray | null;
  const re = new RegExp(THINK_RE.source, 'g');
  while ((match = re.exec(text)) !== null) {
    const content = match[1].trim();
    if (content && !alreadySeen.has(content)) {
      alreadySeen.add(content);
      results.push({
        content,
        startIndex: match.index,
        endIndex: match.index + match[0].length,
        text: match[0],
      });
    }
  }
  return results;
}

export function stripThinkTags(text: string): string {
  return text.replace(THINK_RE, '').trim();
}

export function getDisplayableText(text: string): string {
  // Strip think blocks, handling three streaming states:
  //   1. Complete:   <think>...</think>  → removed
  //   2. Unterminated: <think>... (no close) → trim from <think> onward
  //   3. Partial opening: <think (no > yet)   → trim from <think onward
  let result = text;
  let changed = true;
  while (changed) {
    changed = false;

    // Strip complete <think>...</think> blocks
    const stripped = result.replace(/<think>[\s\S]*?<\/think>/g, '');
    if (stripped !== result) {
      result = stripped;
      changed = true;
      continue;
    }

    // Trim from unclosed <think> onward
    const openTag = result.indexOf('<think>');
    if (openTag !== -1 && !result.includes('</think>', openTag)) {
      result = result.slice(0, openTag);
      changed = true;
      continue;
    }

    // Trim from partial <think (missing >) — streaming artifact
    const partial = result.indexOf('<think');
    if (partial !== -1 && !result.startsWith('<think>', partial)) {
      result = result.slice(0, partial);
      changed = true;
    }
  }
  return result;
}
