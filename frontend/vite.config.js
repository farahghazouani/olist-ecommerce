import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000', // ⚠️ Remplacez 8000 par le port réel de votre backend Python/Node
        changeOrigin: true,
        secure: false,
      },
    },
  },
});