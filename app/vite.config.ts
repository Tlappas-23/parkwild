import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The map library alone is ~230 KB gzipped, which is more than the whole
// initial-JS budget (200 KB). It is therefore split into its own chunk and
// imported lazily by the map page; the budget script measures the entry chunk
// only and reports the lazy chunks separately. Same for three/R3F.
export default defineConfig({
  plugins: [react()],
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
