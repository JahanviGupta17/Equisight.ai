import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],

  server: {
    // Proxy all /api requests to FastAPI so we never hit CORS in dev
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
        // Suppress "connect ECONNREFUSED" noise when the backend isn't running yet.
        // The frontend handles fetch failures gracefully — these are not real errors.
        configure: (proxy) => {
          proxy.on('error', (err, _req, res) => {
            if (err.code === 'ECONNREFUSED') {
              // Backend not up yet — return a clean 503 instead of crashing the proxy log
              if (res && !res.headersSent && typeof res.writeHead === 'function') {
                res.writeHead(503, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ detail: 'Backend not available' }));
              }
              return; // swallow the noisy Vite log
            }
            // Re-log anything that isn't a simple connection refusal
            console.error('[proxy]', err.message);
          });
        },
      },
    },
    // Inject a permissive CSP for development that allows Vite's HMR + eval
    headers: {
      'Content-Security-Policy': [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "connect-src 'self' http://127.0.0.1:8000 ws://127.0.0.1:* wss://127.0.0.1:*",
        "img-src 'self' data: blob:",
      ].join('; '),
    },
  },
})
