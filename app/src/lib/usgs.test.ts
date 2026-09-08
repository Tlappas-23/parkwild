import { test } from "node:test";
import assert from "node:assert/strict";
import { fetchElevation, parseElevation } from "./usgs";

test("an elevation is read from the service's body, and anything else is no elevation", () => {
  assert.equal(parseElevation('{"value":"1473.69"}'), 1473.69);
  // The body the service returned for Old Faithful's coordinate.
  assert.equal(
    parseElevation(
      '{"location":{"x":-110.828,"y":44.4605,"spatialReference":{"wkid":4326,"latestWkid":4326}},"locationId":0,"value":"2248.393066406","rasterId":81357,"resolution":1}',
    ),
    2248.393066406,
  );
  // Off its raster the service answers HTTP 200 with plain text.
  assert.equal(parseElevation("Call failed.  [Failed cloud operation: Open, Path: /vsimem/_0000015D.aux.xml]"), null);
  // The no-data sentinel.
  assert.equal(parseElevation('{"value":"-1000000"}'), null);
  assert.equal(parseElevation('{"value":"abc"}'), null);
  assert.equal(parseElevation("{}"), null);
  assert.equal(parseElevation("null"), null);
});

test("two reads of the same spot ask the service once", async () => {
  const real = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response('{"value":"1473.69"}', { status: 200 });
  };
  try {
    assert.equal(await fetchElevation(-110.828, 44.4605), 1473.69);
    assert.equal(await fetchElevation(-110.828, 44.4605), 1473.69);
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = real;
  }
});
