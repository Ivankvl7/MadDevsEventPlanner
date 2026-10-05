import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В dev-режиме /api проксируется на backend: один origin, без CORS, cookie работают.
const backend = process.env.VITE_BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: backend, changeOrigin: false } },
  },
});
