import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  base: '/static/dist/',
  build: {
    outDir: path.resolve(import.meta.dirname, '../deepvision_django/static/dist'),
    emptyOutDir: true,
  },
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/cameras': 'http://127.0.0.1:8000',
      '/recordings': 'http://127.0.0.1:8000',
      '/evidence': 'http://127.0.0.1:8000',
      '/alerts': 'http://127.0.0.1:8000',
      '/static': 'http://127.0.0.1:8000',
    },
  },
});
