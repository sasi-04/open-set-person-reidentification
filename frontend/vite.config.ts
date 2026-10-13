import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The backend listens on 8000 by default (start.ps1 -Port changes it; then set REID_BACKEND_URL to match).
// During development every /api call is forwarded there, so the browser never needs CORS.
const BACKEND = process.env.REID_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // "@/services/api" means "src/services/api" everywhere in the code.
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: { "/api": { target: BACKEND, changeOrigin: true } },
  },
  build: {
    chunkSizeWarningLimit: 900,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    restoreMocks: true,
    testTimeout: 40_000,
  },
});
