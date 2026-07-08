import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { getDisplayableText } from './think';

const renderer = new marked.Renderer();
renderer.code = (code: unknown) => {
  const { text, lang } = code as { text: string; lang?: string };
  const language = lang || 'text';
  const safeCode = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  return `<div class="code-block-wrapper">
    <div class="code-block-header">
      <span class="code-lang">${language}</span>
      <button class="code-copy-btn" type="button" aria-label="复制代码">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 13v4"/><path d="M12 17h.01"/></svg>
        <span class="copy-label">复制</span>
      </button>
    </div>
    <pre><code class="language-${language}">${safeCode}</code></pre>
  </div>`;
};

export function renderMarkdown(text: string): string {
  const raw = marked.parse(text, { async: false, breaks: true, renderer }) as string;
  return DOMPurify.sanitize(raw) as unknown as string;
}

export function formatContent(text: string): string {
  return renderMarkdown(getDisplayableText(text));
}

export function formatContentRaw(text: string): string {
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML.replace(/\n/g, '<br>');
}
