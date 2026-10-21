import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

const isVercel = process.env.VERCEL === '1' || process.env.BUILD_TARGET?.trim() === 'vercel';

export default defineConfig({
  plugins: [react()],
  base: isVercel ? '/' : (process.env.VITE_BASE_PATH || '/static/dist/'),
  build: {
    outDir: isVercel ? 'dist' : path.resolve(import.meta.dirname, '../deepvision_django/static/dist'),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom')) {
            return 'vendor';
          }
          if (id.includes('translations') || id.includes('i18nContext') || id.includes('/i18n/')) {
            return 'i18n';
          }
        },
      },
    },
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
