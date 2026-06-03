import React, { useMemo, useRef, useEffect, useCallback } from 'react';
import { formatContent } from '../../utils/markdown';

interface Props {
  text: string;
  className?: string;
}

export default function Markdown({ text, className }: Props) {
  const html = useMemo(() => formatContent(text), [text]);
  const ref = useRef<HTMLDivElement>(null);

  const handleCopy = useCallback((e: MouseEvent) => {
    const btn = (e.target as HTMLElement).closest('.code-copy-btn') as HTMLButtonElement | null;
    if (!btn) return;
    const wrapper = btn.closest('.code-block-wrapper');
    const codeEl = wrapper?.querySelector('code');
    if (!codeEl) return;
    const codeText = codeEl.textContent || '';
    navigator.clipboard.writeText(codeText).then(() => {
      const label = btn.querySelector('.copy-label');
      if (label) label.textContent = '已复制';
      btn.classList.add('copied');
      setTimeout(() => {
        if (label) label.textContent = '复制';
        btn.classList.remove('copied');
      }, 1500);
    }).catch(() => {
      // Fallback: select and copy manually
      const range = document.createRange();
      range.selectNodeContents(codeEl);
      const sel = window.getSelection();
      if (sel) {
        sel.removeAllRanges();
        sel.addRange(range);
        document.execCommand('copy');
        sel.removeAllRanges();
        const label = btn.querySelector('.copy-label');
        if (label) label.textContent = '已复制';
        btn.classList.add('copied');
        setTimeout(() => {
          if (label) label.textContent = '复制';
          btn.classList.remove('copied');
        }, 1500);
      }
    });
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.addEventListener('click', handleCopy);
    return () => el.removeEventListener('click', handleCopy);
  }, [handleCopy]);

  return (
    <div
      ref={ref}
      className={`markdown-body ${className || ''}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
