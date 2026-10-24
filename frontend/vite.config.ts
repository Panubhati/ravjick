/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // In development, the Vite server forwards /api to the FastAPI server.
  server: { proxy: { "/api": "http://localhost:8000" } },
  test: { environment: "node" },
});
