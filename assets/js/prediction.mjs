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

// While we're moving, the snapshot is *expected* to trail the prediction by about
// speed × round-trip: our verb reaches the server late, and its snapshot reaches us
// late. That gap is in-flight latency, not error — so within this allowance a moving
// body's prediction is left alone rather than dragged back toward a stale position
// (which would quietly reintroduce the input lag prediction exists to remove).
// Beyond it something genuinely desynced (a lost input, a rejected verb): adopt the
// server's word outright. 15 world units ≈ a 300ms round trip at a full run.
const ALLOWANCE = 15;
// At rest there is no in-flight motion: the server catches up within a round-trip and
// whatever error remains is real drift, bled away a fraction per snapshot so the
// correction glides rather than pops.
const BLEED = 0.1;

export function reconcile(predictedX, serverX, moving) {
  const err = serverX - predictedX;
  if (Math.abs(err) > ALLOWANCE) return serverX;
  return moving ? predictedX : predictedX + err * BLEED;
}
