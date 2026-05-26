import React, { useRef, useEffect } from 'react';
import type { WidgetDisplay } from '../../api/types';

const WIDGET_CSP =
  "default-src 'unsafe-inline' data:; script-src 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'unsafe-inline'; img-src data: https:; media-src data: https:; font-src https://cdn.jsdelivr.net; connect-src 'none'; frame-src 'none';";

const VAR_MAPPING: Record<string, string> = {
  '--color-background-primary': '--canvas',
  '--color-background-secondary': '--surface-soft',
  '--color-text-primary': '--ink',
  '--color-text-secondary': '--body',
  '--color-border-primary': '--hairline',
  '--color-border-secondary': '--hairline',
  '--color-accent-primary': '--accent',
};

const FALLBACKS: Record<string, string> = {
  '--color-background-primary': '#fdfcfc',
  '--color-background-secondary': '#f8f7f7',
  '--color-text-primary': '#201d1d',
  '--color-text-secondary': '#424245',
  '--color-border-primary': 'rgba(15,0,0,0.10)',
  '--color-border-secondary': 'rgba(15,0,0,0.10)',
  '--color-accent-primary': '#007aff',
};

function buildCssVars(): string {
  const styles = getComputedStyle(document.documentElement);
  const lines: string[] = [];
  for (const [spec, token] of Object.entries(VAR_MAPPING)) {
    const val = styles.getPropertyValue(token).trim() || FALLBACKS[spec] || '';
    lines.push(`${spec}: ${val};`);
  }
  return lines.join('\n');
}

interface Props {
  widget: WidgetDisplay;
}

export default function WidgetFrame({ widget }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const cssVars = buildCssVars();
  const height = Math.min(widget.height || 400, 1200);

  const srcdoc = `<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="${WIDGET_CSP.replace(/"/g, '&quot;')}">
<style>:root { ${cssVars} } body { font-family: system-ui, sans-serif; margin: 0; padding: 12px; }</style>
</head>
<body>${widget.html}</body>
</html>`;

  return (
    <div className="widget-container" style={{ margin: '12px 0' }}>
      {widget.title && (
        <div className="widget-title" style={{ fontSize: 12, color: 'var(--mute)', marginBottom: 8, fontFamily: 'var(--font-mono)' }}>
          [widget] {widget.title}
        </div>
      )}
      <iframe
        ref={iframeRef}
        sandbox="allow-scripts"
        srcDoc={srcdoc}
        style={{
          width: '100%',
          height: `${height}px`,
          border: '1px solid var(--hairline)',
          borderRadius: 'var(--radius-sm)',
          background: 'var(--canvas)',
        }}
      />
    </div>
  );
}
