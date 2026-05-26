import React, { useMemo } from 'react';
import { formatContent } from '../../utils/markdown';

interface Props {
  text: string;
  className?: string;
}

export default function Markdown({ text, className }: Props) {
  const html = useMemo(() => formatContent(text), [text]);
  return (
    <div
      className={`markdown-body ${className || ''}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
