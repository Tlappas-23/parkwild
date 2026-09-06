// Transformers.js runs its models on onnxruntime-web, whose wasm it would fetch
// from a CDN the page's content-security policy does not allow. Copy the two
// files it needs into public/ort/ at build time so they ship with the app.
import { copyFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "node_modules", "onnxruntime-web", "dist");
const dst = join(here, "..", "public", "ort");
mkdirSync(dst, { recursive: true });
for (const f of ["ort-wasm-simd-threaded.jsep.mjs", "ort-wasm-simd-threaded.jsep.wasm"]) {
  if (existsSync(join(src, f))) copyFileSync(join(src, f), join(dst, f));
  else console.warn(`copy-ort: ${f} not found`);
}
