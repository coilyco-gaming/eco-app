/// <reference types="vitest/config" />
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

// Dev server proxies API-ish routes to the fused Python service so
// `make frontend-dev` against `make http` behaves like production,
// where eco_mcp_app.http_app serves the built SPA itself.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/info": "http://localhost:4000",
      "/preview": "http://localhost:4000",
      "/jobs": "http://localhost:4000",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
  },
})
