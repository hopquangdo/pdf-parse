import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The built bundle (dist/) is served by FastAPI at /app/, in the same process as the API.
export default defineConfig({
  base: '/app/',
  plugins: [react()],
  build: { sourcemap: false, chunkSizeWarningLimit: 900 },
  server: {
    port: 5173,
    proxy: { '/extractions': 'http://127.0.0.1:8000', '/exports': 'http://127.0.0.1:8000', '/health': 'http://127.0.0.1:8000' },
  },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
});
