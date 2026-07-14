import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    hmr: {
      overlay: true,
    },
    proxy: {
      '/v1': 'http://127.0.0.1:8001',
      '/chat': 'http://127.0.0.1:8001',
      '/human-input': 'http://127.0.0.1:8001',
      '/abort': 'http://127.0.0.1:8001',
      '/sessions': 'http://127.0.0.1:8001',
      '/session': 'http://127.0.0.1:8001',
      '/api': 'http://127.0.0.1:8001',
      '/personas': 'http://127.0.0.1:8001',
      '/capabilities': 'http://127.0.0.1:8001',
      '/connectors': 'http://127.0.0.1:8001',
      '/knowledge': 'http://127.0.0.1:8001',
      '/channels': 'http://127.0.0.1:8001',
      '/models': 'http://127.0.0.1:8001',
      '/upload': 'http://127.0.0.1:8001',
      '/skills': 'http://127.0.0.1:8001',
      '/export': 'http://127.0.0.1:8001',
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
});
