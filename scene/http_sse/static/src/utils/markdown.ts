import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { getDisplayableText } from './think';

export function renderMarkdown(text: string): string {
  const raw = marked.parse(text, { async: false }) as string;
  return DOMPurify.sanitize(raw);
}

export function formatContent(text: string): string {
  return renderMarkdown(getDisplayableText(text));
}

export function formatContentRaw(text: string): string {
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML.replace(/\n/g, '<br>');
}
