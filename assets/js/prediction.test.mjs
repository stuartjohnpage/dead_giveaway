import { test } from "node:test";
import assert from "node:assert/strict";
import { advance, reconcile } from "./prediction.mjs";

// Speeds must mirror DeadGiveaway.World: walk 1.25 / run 2.5 world units per 50ms tick.
test("advance applies the verb's speed over real time", () => {
  assert.equal(advance(0, "walk", 50), 1.25); // one tick's worth of walking
  assert.equal(advance(0, "run", 100), 5); // two ticks' worth of running
  assert.equal(advance(7, "walk", 25), 7.625); // fractional frames scale linearly
});

test("advance under stop (or an unknown verb) holds position", () => {
  assert.equal(advance(10, "stop", 1000), 10);
  assert.equal(advance(10, "teleport", 1000), 10);
});

test("a moving body ignores the expected in-flight trail — no reintroduced lag", () => {
  // The server's word trails a runner by ~speed × round-trip; that's latency, not
  // error, so the prediction must stand rather than get dragged back.
  assert.equal(reconcile(100, 95, true), 100);
});

test("at rest, residual drift bleeds gently toward the server's word", () => {
  // Stopped, the server has caught up — a leftover gap is real drift. One snapshot
  // corrects a fraction of it (0.1), so the fix glides instead of popping.
  assert.equal(reconcile(10, 8, false), 9.8);
});

test("at rest with no error, reconcile is a fixed point", () => {
  assert.equal(reconcile(5, 5, false), 5);
});

test("repeated bleeds converge onto the server position", () => {
  let x = 10;
  for (let i = 0; i < 100; i++) x = reconcile(x, 8, false);
  assert.ok(Math.abs(x - 8) < 0.01, `x=${x}`);
});

test("a genuine desync beyond the allowance snaps to the server outright", () => {
  // Bigger than any round-trip can explain (≈15 units): a lost input or rejected
  // verb — trust the server immediately, moving or not.
  assert.equal(reconcile(100, 50, true), 50);
  assert.equal(reconcile(50, 100, false), 100);
});
