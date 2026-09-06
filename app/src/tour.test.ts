import { test } from "node:test";
import assert from "node:assert/strict";
import { bearingDeg, cruisePitch, cruiseZoom, DRIVE_MAX_MS, DRIVE_MIN_MS, DRIVE_PITCH_HIGH, DRIVE_PITCH_LOW, DRIVE_ZOOM_MAX, DRIVE_ZOOM_MIN, haversineM, headingAt, legDurationMs, metersPerPixel, pointAt, resample } from "./tour";

// A road with a vertex every 7 to 90 m, the shape that broke resample_v1 (E-047).
function wigglyRoad(n = 400): number[][] {
  const pts: number[][] = [[-110.5, 44.6]];
  let seed = 7;
  const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  for (let i = 0; i < n; i++) { const [x, y] = pts[pts.length - 1]; pts.push([x + 0.00008 + rnd() * 0.0009, y + (rnd() - 0.5) * 0.0004]); }
  return pts;
}

test("haversine and bearing on known pairs", () => {
  assert.ok(Math.abs(haversineM(0, 0, 0, 1) - 111195) < 50);            // one degree of latitude
  assert.equal(Math.round(bearingDeg([0, 0], [0, 1])), 0);               // due north
  assert.equal(Math.round(bearingDeg([0, 0], [1, 0])), 90);              // due east
});

test("resample keeps one running distance: total equals the true length and every gap is the step", () => {
  const road = wigglyRoad();
  let truth = 0;
  for (let i = 1; i < road.length; i++) truth += haversineM(road[i - 1][0], road[i - 1][1], road[i][0], road[i][1]);
  const rs = resample(road, 25);
  assert.ok(Math.abs(rs.total - truth) < 0.5, `total ${rs.total} vs ${truth}`);
  for (let k = 1; k < rs.cum.length - 1; k++) assert.ok(Math.abs(rs.cum[k] - rs.cum[k - 1] - 25) < 1e-6);
  assert.deepEqual(pointAt(rs, 0), road[0]);
  assert.deepEqual(pointAt(rs, rs.total + 10), road[road.length - 1]);
});

test("the heading never collapses at the end of the path", () => {
  const rs = resample([[0, 0], [0.01, 0], [0.02, 0]], 25);               // due east, ~2.2 km
  assert.equal(Math.round(headingAt(rs, 0, 120)), 90);
  assert.equal(Math.round(headingAt(rs, rs.total - 3, 120)), 90);       // E-047: this swung to north
  assert.equal(Math.round(headingAt(rs, rs.total, 120)), 90);
});

test("the cruise climbs with the leg and stays inside its bounds", () => {
  const short = legDurationMs(300), long = legDurationMs(46_000);
  assert.equal(short, DRIVE_MIN_MS);
  assert.equal(long, DRIVE_MAX_MS);
  const zShort = cruiseZoom(300, short, 37), zLong = cruiseZoom(46_000, long, 37);
  assert.equal(zShort, DRIVE_ZOOM_MAX);
  assert.ok(zLong > DRIVE_ZOOM_MIN && zLong < 13, `46 km cruises at ${zLong}`);
  assert.ok(cruisePitch(DRIVE_ZOOM_MIN) === DRIVE_PITCH_HIGH && cruisePitch(DRIVE_ZOOM_MAX) === DRIVE_PITCH_LOW);
  // the screen speed the zoom was chosen for: 46 km over 16 s at that zoom is about 110 px/s
  const pxPerS = (46_000 / (long / 1000)) / metersPerPixel(zLong, 37);
  assert.ok(Math.abs(pxPerS - 110) < 1, `${pxPerS} px/s`);
});
