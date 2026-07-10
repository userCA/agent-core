import React, { useMemo, useCallback } from 'react';
import { formatContent } from '../../utils/markdown';

interface Props {
  text: string;
  className?: string;
}

export default function Markdown({ text, className }: Props) {
  const html = useMemo(() => formatContent(text), [text]);

  const handleCopy = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const btn = (e.target as HTMLElement).closest('.code-copy-btn') as HTMLButtonElement | null;
    if (!btn) return;
    const wrapper = btn.closest('.code-block-wrapper');
    const codeEl = wrapper?.querySelector('code');
    if (!codeEl) return;
    const codeText = codeEl.textContent || '';
    const svg = btn.querySelector('svg');
    const originalSvg = svg ? svg.outerHTML : '';
    const checkSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';

    const showCopied = () => {
      if (svg) svg.outerHTML = checkSvg;
      btn.classList.add('copied');
      setTimeout(() => {
        const s = btn.querySelector('svg');
        if (s) s.outerHTML = originalSvg;
        btn.classList.remove('copied');
      }, 1500);
    };

    navigator.clipboard.writeText(codeText).then(showCopied).catch(() => {
      const range = document.createRange();
      range.selectNodeContents(codeEl);
      const sel = window.getSelection();
      if (sel) {
        sel.removeAllRanges();
        sel.addRange(range);
        document.execCommand('copy');
        sel.removeAllRanges();
        showCopied();
      }
    });
  }, []);

  return (
    <div
      className={`markdown-body ${className || ''}`}
      dangerouslySetInnerHTML={{ __html: html }}
      onClick={handleCopy}
    />
  );
}
