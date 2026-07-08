import React from 'react';
import ReactDOM from 'react-dom/client';
import './theme/tokens.css';
import './theme/radix-overrides.css';

document.documentElement.classList.add('h5-html');
const root = ReactDOM.createRoot(document.getElementById('root')!);

import('./h5/App').then(({ default: H5App }) => {
  root.render(
    <React.StrictMode><H5App /></React.StrictMode>
  );
});
