// Headless check of the tour camera, because the browser the assistant drives
// keeps its tab hidden and no animation runs there (E-021). Starts the real
// Chrome headless with software WebGL, opens the site, starts the tour,
// presses Next at a chosen second (and again at NEXT2 if set), and writes a
// camera sample every 200 ms plus a screenshot every SHOT_MS to outdir. No
// dependencies: Node's own WebSocket over the DevTools protocol.
//
//   node app/scripts/tour-probe.mjs "https://tlappas-23.github.io/parkwild/?park=zion" /tmp/probe 44 8
//   DRIVE=off NEXT2=40 SHOT_MS=1500 node app/scripts/tour-probe.mjs http://127.0.0.1:4173/?park=zion /tmp/probe 64 8
//
// It found E-048: the camera's target elevation was 0 m under a 1.5 km high
// park during every drive, which the state check in E-046 could not see.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";

const [url, outdir, secondsArg = "24", nextAtArg = "6"] = process.argv.slice(2);
const SECONDS = +secondsArg,
  NEXT_AT = +nextAtArg;
const DRIVE = process.env.DRIVE || "on";
const SHOT_MS = +(process.env.SHOT_MS || 700);
const NEXT2 = +(process.env.NEXT2 || 0);
mkdirSync(outdir, { recursive: true });
const port = 9333 + Math.floor(Math.random() * 100);
const chrome = spawn(
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  [
    "--headless=new",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${outdir}/profile`,
    "--window-size=1100,720",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
    "--no-first-run",
    "--hide-scrollbars",
    "--mute-audio",
    "about:blank",
  ],
  { stdio: "ignore" },
);
const done = async (code = 0) => {
  try {
    chrome.kill("SIGKILL");
  } catch {
    /* ignore */
  }
  process.exit(code);
};
process.on("SIGINT", () => done(1));

let ws;
let idc = 0;
const pending = new Map();
const events = [];
async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await fetch(`http://127.0.0.1:${port}/json`).then((r) => r.json());
      const page = list.find((t) => t.type === "page");
      if (page) {
        ws = new WebSocket(page.webSocketDebuggerUrl);
        break;
      }
    } catch {
      /* ignore */
    }
    await sleep(500);
  }
  if (!ws) throw new Error("no page target");
  await new Promise((res, rej) => {
    ws.onopen = res;
    ws.onerror = rej;
  });
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pending.has(d.id)) {
      pending.get(d.id)(d);
      pending.delete(d.id);
    } else if (d.method) events.push(d);
  };
}
const send = (method, params = {}) =>
  new Promise((res) => {
    const id = ++idc;
    pending.set(id, res);
    ws.send(JSON.stringify({ id, method, params }));
  });
async function evaluate(expression, awaitPromise = true) {
  const r = await send("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
  if (r.result?.exceptionDetails)
    throw new Error("page: " + (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text));
  return r.result?.result?.value;
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "jpeg", quality: 55 });
  if (r.result?.data) writeFileSync(`${outdir}/${name}.jpg`, Buffer.from(r.result.data, "base64"));
}

try {
  await connect();
  await send("Runtime.enable");
  await send("Page.enable");
  await send("Log.enable");
  await send("Page.navigate", { url: new URL(url).origin + "/parkwild/404-probe" });
  await sleep(1500);
  await evaluate(`localStorage.setItem("parkwild:drive", ${JSON.stringify(DRIVE)}); 1`);
  await send("Page.navigate", { url });
  // wait for the store and the map object (found through the React fiber of the map container)
  const found = await evaluate(`(async () => {
    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    for (let i = 0; i < 120; i++) {
      const el = document.querySelector('.maplibregl-map');
      if (window.__parkwildStore && el) {
        const key = Object.keys(el).find(k => k.startsWith('__reactFiber'));
        let f = el[key], map = null;
        while (f && !map) { let h = f.memoizedState; while (h) { const c = h.memoizedState && h.memoizedState.current; if (c && typeof c.getBearing === 'function' && typeof c.jumpTo === 'function') { map = c; break; } h = h.next; } f = f.return; }
        if (map) { window.__m = map; return { ok: true, waited: i * 500 }; }
      }
      await sleep(500);
    }
    return { ok: false, store: !!window.__parkwildStore, el: !!document.querySelector('.maplibregl-map') };
  })()`);
  console.log("map:", JSON.stringify(found));
  if (!found.ok) await done(2);
  // wait for tiles once, so the first stop is not confounded by initial loading
  await evaluate(
    `new Promise(r => { const m = window.__m; if (m.loaded()) return r(1); m.once('idle', () => r(2)); setTimeout(() => r(0), 20000); })`,
  );
  await evaluate(`(() => { window.__samples = []; window.__t0 = performance.now(); const m = window.__m, S = window.__parkwildStore;
    window.__err = []; m.on('error', e => window.__err.push(String(e && e.error && e.error.message || e))); m.getCanvas().addEventListener('webglcontextlost', () => window.__err.push('WEBGL CONTEXT LOST'));
    window.__cam = () => { const c = m.getCenter(); const st = S.getState(); const gl = m.painter && m.painter.context && m.painter.context.gl; const tr = m.transform; const mvp = tr.modelViewProjectionMatrix || tr.mercatorMatrix || []; return { elev: (Number.isFinite(tr.elevation) ? +tr.elevation.toFixed(1) : String(tr.elevation)), minE: tr.minElevationForCurrentTile, mvpBad: Array.from(mvp).some(v => !Number.isFinite(v)), frz: m._elevationFreeze, lost: gl ? gl.isContextLost() : null, tiles: m.areTilesLoaded(), terr: !!m.getTerrain(), t: +((performance.now() - window.__t0) / 1000).toFixed(2), lon: +c.lng.toFixed(5), lat: +c.lat.toFixed(5), z: +m.getZoom().toFixed(2), b: +m.getBearing().toFixed(1), p: +m.getPitch().toFixed(1), mv: m.isMoving(), ld: m.loaded(), stop: st.tour?.stop, drv: st.tourDrive ? Math.round(st.tourDrive.distanceM) : null, pad: m.getPadding().right }; };
    window.__iv = setInterval(() => window.__samples.push(window.__cam()), 200);
    window.__frames = 0; const tick = () => { window.__frames++; requestAnimationFrame(tick); }; requestAnimationFrame(tick);
    return 1; })()`);
  await evaluate(`window.__parkwildStore.getState().startTour(); 1`);
  const T0 = Date.now();
  let nextDone = false,
    next2Done = false;
  let k = 0;
  while ((Date.now() - T0) / 1000 < SECONDS) {
    const t = (Date.now() - T0) / 1000;
    if (NEXT2 && !next2Done && t >= NEXT2) {
      await evaluate(`window.__parkwildStore.getState().tourNext(); 1`);
      next2Done = true;
      console.log("next2 at", t.toFixed(1));
    }
    if (!nextDone && t >= NEXT_AT) {
      await evaluate(`window.__parkwildStore.getState().tourNext(); 1`);
      nextDone = true;
      console.log("next at", t.toFixed(1));
    }
    await shot(`f${String(k++).padStart(2, "0")}_${t.toFixed(1)}s`);
    await sleep(SHOT_MS);
  }
  const samples = await evaluate(
    `JSON.stringify({ frames: window.__frames, vis: document.visibilityState, samples: window.__samples, mapErrors: window.__err, style: (() => { const st = window.__m.getStyle(); return st.layers.filter(l => /mask|imagery|hillshade|outline/.test(l.id)).map(l => ({ id: l.id, type: l.type, layout: l.layout, paint: l.paint })); })(), maxB: window.__m.getMaxBounds() && window.__m.getMaxBounds().toArray() })`,
  );
  writeFileSync(`${outdir}/samples.json`, samples);
  const s = JSON.parse(samples);
  console.log(
    "frames rendered:",
    s.frames,
    "visibility:",
    s.vis,
    "samples:",
    s.samples.length,
    "mapErrors:",
    JSON.stringify(s.mapErrors).slice(0, 400),
  );
  console.log("maxBounds:", JSON.stringify(s.maxB), "layers:", JSON.stringify(s.style).slice(0, 900));
  for (const x of s.samples.filter((_, i) => i % 3 === 0)) console.log(JSON.stringify(x));
  const errs = events.filter(
    (e) =>
      e.method === "Runtime.exceptionThrown" || (e.method === "Log.entryAdded" && e.params.entry.level === "error"),
  );
  console.log("errors:", errs.length);
  for (const e of errs.slice(0, 8)) console.log("  ", JSON.stringify(e.params).slice(0, 300));
  await done(0);
} catch (e) {
  console.error("probe failed:", e.message);
  await done(1);
}
