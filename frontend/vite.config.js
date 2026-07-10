import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    watch: {
      // Docker Desktop on Windows doesn't reliably forward filesystem change
      // events across the bind mount, so chokidar's native watcher misses
      // edits made from the host. Polling guarantees changes are picked up.
      usePolling: true,
      interval: 300,
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
  },
})
