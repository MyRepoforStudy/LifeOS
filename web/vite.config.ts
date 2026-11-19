import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

const backend = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "icons/apple-touch-icon.png"],
      manifest: {
        name: "LifeOS",
        short_name: "LifeOS",
        description: "Личная RPG: опыт за реальные действия",
        lang: "ru",
        start_url: "/",
        scope: "/",
        display: "standalone",
        orientation: "portrait",
        background_color: "#0b0d11",
        theme_color: "#0b0d11",
        icons: [
          { src: "icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icons/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // Only the app shell is cached. API calls always go to the network:
        // there is no offline mode by design (docs/decisions.md, item 16).
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/health/],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: { "/api": backend, "/health": backend },
  },
  preview: {
    port: 4173,
    proxy: { "/api": backend, "/health": backend },
  },
});
