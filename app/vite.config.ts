import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// The map library alone is ~230 KB gzipped, which is more than the whole
// initial-JS budget (200 KB). It is therefore split into its own chunk and
// imported lazily by the map page; the budget script measures the entry chunk
// only and reports the lazy chunks separately. Same for three/R3F.
// GitHub Pages serves a project site under /<repo>/; the deploy workflow sets
// VITE_BASE=/parkwild/. Locally the default "/" keeps `npm run dev` simple.
export default defineConfig({
  base: process.env.VITE_BASE ?? "/",
  plugins: [
    react(),
    // Offline after first load (BUILD_SPEC.md Phase 7): the app shell and the
    // data files are precached; basemap tiles and glyphs are cached as they are
    // seen, capped so the cache cannot grow without bound. The web manifest is
    // the hand-written one in public/, not a generated one.
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: "script-defer",   // an external registerSW.js; an inline script would violate the CSP
      manifest: false,
      includeAssets: ["icon.svg", "manifest.webmanifest"],
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,webmanifest}", "data/**/*.{geojson,json}"],
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024,
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.hostname === "tiles.openfreemap.org",
            handler: "CacheFirst",
            options: { cacheName: "basemap", expiration: { maxEntries: 400, maxAgeSeconds: 30 * 24 * 3600 } },
          },
          {
            urlPattern: ({ url }) => url.pathname.includes("/models/"),
            handler: "CacheFirst",
            options: { cacheName: "models", expiration: { maxEntries: 40 } },
          },
        ],
      },
    }),
  ],
  build: {
    target: "es2022",
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          maplibre: ["maplibre-gl"],
          three: ["three", "@react-three/fiber"],
        },
      },
    },
  },
});
