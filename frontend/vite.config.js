import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    chunkSizeWarningLimit: 1600, // Plotly is large, and it is loaded only on the dashboard
  },
  test: {
    environment: "jsdom",
    globals: true, // lets Testing Library clean up after each test
    setupFiles: "./src/test/setup.js",
  },
});