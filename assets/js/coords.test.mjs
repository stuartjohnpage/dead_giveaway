import { test } from "node:test";
import assert from "node:assert/strict";
import { worldToScreen, screenToWorld } from "./coords.mjs";

// World: x in [0, worldW], y in [0, worldH]. Screen: a padded box.
const view = { worldW: 1000, worldH: 50, screenW: 800, screenH: 400, pad: 20 };

test("the world origin maps to the padded top-left corner", () => {
  const { sx, sy } = worldToScreen(0, 0, view);
  assert.equal(sx, 20);
  assert.equal(sy, 20);
});

test("the far world corner maps to the padded bottom-right corner", () => {
  const { sx, sy } = worldToScreen(1000, 50, view);
  assert.equal(sx, 780);
  assert.equal(sy, 380);
});

test("screenToWorld inverts worldToScreen (round-trip)", () => {
  const { sx, sy } = worldToScreen(640, 30, view);
  const { wx, wy } = screenToWorld(sx, sy, view);
  assert.ok(Math.abs(wx - 640) < 1e-9, `wx=${wx}`);
  assert.ok(Math.abs(wy - 30) < 1e-9, `wy=${wy}`);
});
