import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/chat': 'http://localhost:8001',
      '/human-input': 'http://localhost:8001',
      '/abort': 'http://localhost:8001',
      '/sessions': 'http://localhost:8001',
      '/session': 'http://localhost:8001',
      '/api': 'http://localhost:8001',
      '/personas': 'http://localhost:8001',
      '/capabilities': 'http://localhost:8001',
      '/connectors': 'http://localhost:8001',
      '/knowledge': 'http://localhost:8001',
      '/channels': 'http://localhost:8001',
      '/models': 'http://localhost:8001',
      '/upload': 'http://localhost:8001',
      '/skills': 'http://localhost:8001',
      '/export': 'http://localhost:8001',
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
});
