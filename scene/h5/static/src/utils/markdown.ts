import { marked } from 'marked';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js';
import 'highlight.js/styles/github.css';
import { getDisplayableText } from './think';

const renderer = new marked.Renderer();
renderer.code = (code: string, infostring?: string) => {
  const language = (infostring || '').match(/^\S*/)?.[0] || 'text';
  let highlighted: string;
  if (language && language !== 'text' && hljs.getLanguage(language)) {
    highlighted = hljs.highlight(code || '', { language }).value;
  } else {
    highlighted = hljs.highlightAuto(code || '').value;
  }

  return `<div class="code-block-wrapper">
    <div class="code-block-bar">
      ${language && language !== 'text' ? `<span class="code-lang-label">${language}</span>` : '<span></span>'}
      <button class="code-copy-btn" type="button" aria-label="复制代码">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      </button>
    </div>
    <pre><code class="hljs language-${language}">${highlighted}</code></pre>
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
