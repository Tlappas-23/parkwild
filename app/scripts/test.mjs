// The app's unit tests without another dependency: esbuild (already here for
// Vite) bundles every src/**/*.test.ts into a scratch folder and Node's own
// test runner runs them. Pure modules only (tour maths, names, HTML escaping,
// routing); anything that touches the DOM or MapLibre is checked by the
// headless probes instead (tour-probe.mjs).
import { build } from "esbuild";
import { mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = resolve(new URL("..", import.meta.url).pathname);
const out = join(root, "node_modules", ".tests");
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

function walk(dir) {
  const files = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) files.push(...walk(p));
    else if (/\.test\.tsx?$/.test(name)) files.push(p);
  }
  return files;
}
const entries = walk(join(root, "src"));
if (entries.length === 0) { console.error("no *.test.ts files under src/"); process.exit(1); }
await build({ entryPoints: entries, outdir: out, bundle: true, platform: "node", format: "esm", target: "node22", sourcemap: "inline", logLevel: "error",
  define: { "import.meta.env.BASE_URL": '"/"' } });
const built = readdirSync(out).filter((f) => /\.test\.js$/.test(f)).map((f) => join(out, f));
const r = spawnSync(process.execPath, ["--test", "--enable-source-maps", ...built], { stdio: "inherit" });
process.exit(r.status ?? 1);
