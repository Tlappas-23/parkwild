// Performance budget (BUILD_SPEC.md Phase 7): entry JS under 200 KB gzipped.
// budget; each is capped separately so a regression is still visible.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { join } from "node:path";

const dist = join(process.cwd(), "dist", "assets");
const ENTRY_BUDGET = 200 * 1024;
// Lazy chunks (the map) are reported but not counted against the entry
const CHUNK_BUDGET = { maplibre: 300 * 1024 };
let failed = false;
const rows = [];
for (const f of readdirSync(dist)) {
  if (!f.endsWith(".js")) continue;
  const gz = gzipSync(readFileSync(join(dist, f))).length;
  const raw = statSync(join(dist, f)).size;
  const name = f.split("-")[0];
  let budget = null;
  if (name === "index") budget = ENTRY_BUDGET;
  else if (CHUNK_BUDGET[name]) budget = CHUNK_BUDGET[name];
  const over = budget !== null && gz > budget;
  failed ||= over;
  rows.push({
    file: f,
    raw_kb: (raw / 1024).toFixed(0),
    gzip_kb: (gz / 1024).toFixed(0),
    budget_kb: budget ? (budget / 1024).toFixed(0) : "-",
    status: over ? "OVER" : "ok",
  });
}
console.table(rows);
if (failed) {
  console.error("performance budget exceeded");
  process.exit(1);
}
