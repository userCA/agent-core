import React from 'react';
import { renderToolResult } from '../../utils/tool-result';

interface Props {
  text: string;
}

export default function MediaDetector({ text }: Props) {
  const html = renderToolResult(text);
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
