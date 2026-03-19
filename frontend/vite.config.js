import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: parseInt(process.env.PORT) || 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target:
          process.env.VITE_API_URL ||
          (process.env.DOCKER === "true"
            ? "http://backend:8000"
            : "http://localhost:8002"),
        changeOrigin: true,
      },
    },
  },
});
