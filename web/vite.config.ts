import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const proxy = { "/v1": { target: "http://127.0.0.1:8010", changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
});
