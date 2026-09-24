import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://localhost:8000",
      "/reviews": "http://localhost:8000",
      "/observability": "http://localhost:8000",
    },
  },
});
