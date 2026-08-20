import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
  server: {
    port: 5173,
    // The API is the authority on every number; the dev server only proxies.
    // F1_API_TARGET overrides the port so a second backend -- one bound to
    // F1_BACKEND=supabase, say -- can be driven through the same UI without
    // editing this file.
    proxy: {
      "/api": {
        target: process.env.F1_API_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
