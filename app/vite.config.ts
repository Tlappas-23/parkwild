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
        // The shell is precached; data files are not. Their URLs carry
        // ?v=<hash>, so a content-addressed runtime cache serves each shell
        // exactly the files it was built with, and a visitor's first load does
        // not pull every park's data in the background (E-027).
        globPatterns: ["**/*.{js,css,html,svg,webmanifest}"],
        // The AI runtimes and the onnx wasm are fetched on demand, never precached.
        globIgnores: ["**/ort/**", "**/assets/webllm-*.js", "**/assets/transformers-*.js"],
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024,
        // Data URLs carry ?v=<manifest hash>. Ignoring that parameter when
        // matching the precache means a cached app shell is always served its
        // own cached data, never a newer file from the server: after a deploy,
        // an old shell saw new data and its integrity check refused it (E-023).
        ignoreURLParametersMatching: [/^v$/],
        cleanupOutdatedCaches: true,
        // "autoUpdate" alone only skips waiting on a message the old shell
        // never sends, so a new worker sat in "waiting" for as long as any tab
        // stayed open and the owner kept seeing a build from days before
        // (E-034). Take over at install, claim open pages, and let the app
        // reload on the controller change.
        skipWaiting: true,
        clientsClaim: true,
        runtimeCaching: [
          {
            // vector tiles + fonts, USGS imagery, and the terrain DEM tiles: all immutable in practice
            urlPattern: ({ url }) => ["tiles.openfreemap.org", "basemap.nationalmap.gov"].includes(url.hostname)
              || (url.hostname === "s3.amazonaws.com" && url.pathname.startsWith("/elevation-tiles-prod/")),
            handler: "CacheFirst",
            options: { cacheName: "basemap", expiration: { maxEntries: 900, maxAgeSeconds: 30 * 24 * 3600 }, cacheableResponse: { statuses: [0, 200] } },
          },
          {
            urlPattern: ({ url }) => url.pathname.includes("/data/") && url.searchParams.has("v"),
            handler: "CacheFirst",
            options: { cacheName: "data", expiration: { maxEntries: 80, maxAgeSeconds: 60 * 24 * 3600 }, cacheableResponse: { statuses: [200] } },
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
          // On-device AI: loaded only from the Ask page, after the visitor opts in.
          webllm: ["@mlc-ai/web-llm"],
          transformers: ["@huggingface/transformers"],
        },
      },
    },
  },
});
