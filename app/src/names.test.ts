import { test } from "node:test";
import assert from "node:assert/strict";
import { shortPark } from "./names";
import { esc } from "./html";

test("park names lose their suffix and keep their identity", () => {
  assert.equal(shortPark("Yellowstone National Park"), "Yellowstone");
  assert.equal(shortPark("Wrangell-St. Elias National Park and Preserve"), "Wrangell-St. Elias");
  assert.equal(shortPark("Sequoia and Kings Canyon National Parks"), "Sequoia and Kings Canyon");
  assert.equal(shortPark("National Park of American Samoa"), "American Samoa");
  assert.equal(shortPark("Gateway Arch"), "Gateway Arch");
});

test("popup text from data cannot carry markup", () => {
  assert.equal(esc(`<img src=x onerror="alert(1)"> & 'Bill's' Pass`), "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; &#39;Bill&#39;s&#39; Pass");
  assert.equal(esc("Old Faithful"), "Old Faithful");
});
