import { escapeHtml } from './html';

const AUDIO_EXTS = /\.(mp3|wav|ogg|m4a|flac)(\?|$)/i;
const VIDEO_EXTS = /\.(mp4|mov|webm|m3u8)(\?|$)/i;
const IMG_EXTS = /\.(png|jpg|jpeg|gif|svg|webp)(\?|$)/i;
const URL_RE = /(https?:\/\/[^\s]+)/g;

export function renderToolResult(text: string): string {
  if (!text) return '';

  // Multi-image URLs detection
  const lines = text.trim().split('\n');
  const allImages = lines.length > 1 && lines.every(l => IMG_EXTS.test(l.trim()));
  if (allImages) {
    return lines.map(url =>
      `<img src="${escapeHtml(url.trim())}" alt="generated" class="result-img" />`
    ).join('');
  }

  // audio URL detection
  if (AUDIO_EXTS.test(text)) {
    return `<audio class="result-audio" controls src="${escapeHtml(text.trim())}"></audio>`;
  }

  // video URL detection
  if (VIDEO_EXTS.test(text)) {
    return `<video class="result-video" controls width="100%" src="${escapeHtml(text.trim())}"></video>`;
  }

  // image URL detection
  if (IMG_EXTS.test(text)) {
    return `<img src="${escapeHtml(text.trim())}" alt="result image" class="result-img" />`;
  }

  // JSON detection — render as collapsible code block
  if (/^\s*[\[{]/.test(text) && /[\]}]\s*$/.test(text)) {
    try {
      const parsed = JSON.parse(text);
      const formatted = JSON.stringify(parsed, null, 2);
      const e = escapeHtml(formatted);
      return `<details><summary>JSON (${Object.keys(parsed).length} keys)</summary><pre><code>${e}</code></pre></details>`;
    } catch {
      // not valid JSON, fall through
    }
  }

  // URL linkification
  const linked = text.replace(URL_RE, (url) => {
    const escaped = escapeHtml(url);
    return `<a href="${escaped}" target="_blank" rel="noopener">${escaped}</a>`;
  });

  if (linked !== text) return linked;
  return `<pre style="white-space:pre-wrap;font-family:var(--font-mono);margin:0;">${escapeHtml(text)}</pre>`;
}
