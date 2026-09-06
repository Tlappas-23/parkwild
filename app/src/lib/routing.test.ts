import { test } from "node:test";
import assert from "node:assert/strict";
import { planRoute, routerFor, type Site } from "./routing";
import type { RoadsFile } from "../data/types";

// Four nodes on a line a kilometre apart: two road edges, then a trail.
//   A ─road─ B ─road─ C ─trail─ D
const nodes = [
  [0, 0],
  [0.01, 0],
  [0.02, 0],
  [0.03, 0],
];
const seg = (i: number, j: number, kind: 0 | 1): RoadsFile["edges"][number] => [
  i,
  j,
  1113,
  kind,
  0,
  0,
  [nodes[i], nodes[j]],
];
const roads: RoadsFile = {
  park: "test",
  fetched: "",
  attribution: "",
  names: ["Test Road"],
  nodes,
  edges: [seg(0, 1, 0), seg(1, 2, 0), seg(2, 3, 1)],
};
const site = (id: string, lon: number): Site => ({ id, label: id, lon, lat: 0, kind: "landmark" });

test("driving uses roads only; hiking may take the trail", () => {
  const r = routerFor(roads);
  const drive = r.shortest(0, "drive"),
    hike = r.shortest(0, "hike");
  assert.equal(drive.dist[2], 2226);
  assert.equal(drive.dist[3], Infinity);
  assert.equal(hike.dist[3], 3339);
  assert.deepEqual(
    r.path(hike, 3).map((c) => c[0]),
    [0, 0.01, 0.02, 0.03],
  ); // shared vertices stitched once
});

test("snapping in drive mode never lands on a trail-only node", () => {
  const r = routerFor(roads);
  assert.equal(r.snap(0.03, 0, "hike").node, 3);
  assert.equal(r.snap(0.03, 0, "drive").node, 2);
});

test("the plan visits the sites in the shortest order", () => {
  const r = routerFor(roads);
  const plan = planRoute(r, site("start", 0), [site("far", 0.02), site("near", 0.01)], "drive");
  assert.deepEqual(
    plan.order.map((s) => s.id),
    ["near", "far"],
  );
  assert.equal(plan.legs.length, 2);
  assert.equal(plan.distanceM, 2226);
  assert.deepEqual(plan.unreachable, []);
});
