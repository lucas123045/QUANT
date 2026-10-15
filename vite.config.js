import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Porta da API: 8000 por padrão (QUANT_API_PORT permite rodar outra instância).
const portaApi = process.env.QUANT_API_PORT || "8000";

export default defineConfig({
  root: "web",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    open: true,
    proxy: { "/api": `http://127.0.0.1:${portaApi}` },
  },
  build: { outDir: "../dist", emptyOutDir: true },
});
