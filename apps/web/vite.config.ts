import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "NAC TTS",
        short_name: "NAC TTS",
        description: "Local GPU text-to-speech for long-form listening.",
        theme_color: "#d7e6f4",
        background_color: "#09111d",
        display: "standalone",
        start_url: "/",
        icons: [
          {
            src: "/icon.svg",
            sizes: "512x512",
            type: "image/svg+xml",
            purpose: "any maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith("/api/"),
            handler: "NetworkFirst",
            options: {
              cacheName: "api-cache",
              expiration: {
                maxEntries: 20,
                maxAgeSeconds: 60,
              },
            },
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
