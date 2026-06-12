// Client-side prediction of the local player's own body (#41, DESIGN §9).
//
// The server stays fully authoritative for all gameplay; the client merely applies
// its own verb to its own body the instant a key changes (`advance`) and corrects
// back onto the server's word whenever a snapshot genuinely disagrees (`reconcile`).
// Kept Pixi- and socket-free so it can be unit-tested directly; game.mjs wires it
// to the render ticker and the snapshot stream.

// Movement speeds in world units per server tick — must match DeadGiveaway.World
// (@walk_speed / @run_speed) and the room's 50ms tick, or prediction drifts.
const TICK_MS = 50;
const SPEEDS = { stop: 0, walk: 1.25, run: 2.5 };

// Advance a predicted x by the local verb over `dtMs` of real time (a render frame).
export function advance(x, verb, dtMs) {
  return x + ((SPEEDS[verb] || 0) / TICK_MS) * dtMs;
}

// While the *server's* body is still moving, its word is stale by definition: our
// latest verb and its snapshot are both in transit, so whatever gap we see is
// round-trip latency, not error — and it closes by itself within one round trip,
// because the server integrates the same inputs for the same duration we did.
// Correcting against it drags the body backwards after every stop, chasing
// positions the server has already abandoned. So a moving server body leaves the
// prediction entirely alone; corrections engage only once its word is at rest.
//
// While only *we* are moving (the first round-trip of a fresh keypress, before the
// server's body visibly starts), the same in-flight argument holds — up to an
// allowance. Beyond it something genuinely desynced (a lost or rejected verb that
// will never start the server's body): adopt the server's word outright.
// 15 world units ≈ a 300ms round trip at a full run.
const ALLOWANCE = 15;
// At mutual rest whatever error remains is real drift, bled away a fraction per
// snapshot so the correction glides rather than pops.
const BLEED = 0.1;

export function reconcile(predictedX, serverX, moving, serverMoving) {
  if (serverMoving) return predictedX;
  const err = serverX - predictedX;
  if (Math.abs(err) > ALLOWANCE) return serverX;
  return moving ? predictedX : predictedX + err * BLEED;
}
