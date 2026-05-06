import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Single-page app dev server. The dev proxy forwards `/api/*` to the FastAPI
// process so the browser can use relative URLs everywhere.
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            "/api": {
                target: "http://127.0.0.1:8000",
                changeOrigin: true,
            },
        },
    },
    build: {
        outDir: "dist",
        sourcemap: true,
    },
});
