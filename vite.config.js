import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Local case API (Cheich). App must be opened at localhost:5173 / 127.0.0.1:5173.
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
