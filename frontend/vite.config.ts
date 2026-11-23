import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({mode}) => {
  const localTest = mode === 'local-test';
  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: localTest ? 5174 : 5173,
      strictPort: true,
      proxy: {
        '/api': {
          target: localTest ? 'http://127.0.0.1:8001' : 'http://127.0.0.1:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
  };
});
