import React from 'react';
import ReactDOM from 'react-dom/client';
import './theme/tokens.css';
import './theme/radix-overrides.css';

async function bootstrap() {
  const root = document.getElementById('root')!;
  const params = new URLSearchParams(window.location.search);
  const mode = params.get('mode') || 'h5'; // 默认 H5，?mode=desktop 切换桌面

  if (mode === 'desktop') {
    const { default: DesktopApp } = await import('./desktop/App');
    ReactDOM.createRoot(root).render(
      <React.StrictMode><DesktopApp /></React.StrictMode>
    );
  } else {
    document.documentElement.classList.add('h5-html');
    const { default: H5App } = await import('./h5/App');
    ReactDOM.createRoot(root).render(
      <React.StrictMode><H5App /></React.StrictMode>
    );
  }
}

bootstrap();
