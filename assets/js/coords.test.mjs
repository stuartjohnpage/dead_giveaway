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

// padX/padY override pad per-axis: the arena uses a small horizontal pad (full-width
// track) but a large vertical pad (lanes confined to the floor band).
test("padX/padY inset the axes independently", () => {
  const v = { worldW: 1000, worldH: 50, screenW: 800, screenH: 400, padX: 10, padY: 80 };
  assert.deepEqual(worldToScreen(0, 0, v), { sx: 10, sy: 80 });
  assert.deepEqual(worldToScreen(1000, 50, v), { sx: 790, sy: 320 });
  const { wx, wy } = screenToWorld(...Object.values(worldToScreen(500, 25, v)), v);
  assert.ok(Math.abs(wx - 500) < 1e-9 && Math.abs(wy - 25) < 1e-9);
});

test("padX/padY default to pad when omitted (back-compat)", () => {
  const v = { worldW: 1000, worldH: 50, screenW: 800, screenH: 400, pad: 20 };
  assert.deepEqual(worldToScreen(0, 0, v), { sx: 20, sy: 20 });
});
