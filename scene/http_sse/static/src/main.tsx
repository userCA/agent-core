import React from 'react';
import ReactDOM from 'react-dom/client';
import './theme/tokens.css';

async function bootstrap() {
  const root = document.getElementById('root')!;
  document.documentElement.classList.add('h5-html');

  const { default: H5App } = await import('./h5/App');
  ReactDOM.createRoot(root).render(
    <React.StrictMode><H5App /></React.StrictMode>
  );
}

bootstrap();
