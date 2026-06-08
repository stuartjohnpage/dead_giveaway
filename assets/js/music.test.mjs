import { test } from "node:test";
import assert from "node:assert/strict";

let seq = 0;

// Each test gets a fresh module instance (unique import query) so the module-level
// shared AudioContext doesn't leak between tests, plus fresh WebAudio + fetch stubs that
// record the source/gain nodes the loop creates so we can assert on them.
async function setup() {
  const sources = [];
  const gains = [];
  let fetchCalls = 0;

  class FakeSource {
    constructor() {
      this.started = false;
      this.stopped = false;
      this.loop = false;
      this.buffer = null;
    }
    connect(node) {
      return node; // src.connect(gain).connect(destination) — return the next link
    }
    start() {
      this.started = true;
    }
    stop() {
      this.stopped = true;
    }
    disconnect() {}
  }

  class FakeCtx {
    constructor() {
      this.state = "suspended";
      this.destination = {};
      this.resumeCount = 0;
      this.currentTime = 0;
    }
    async resume() {
      this.state = "running";
      this.resumeCount++;
    }
    async decodeAudioData() {
      return { duration: 1 };
    }
    createBufferSource() {
      const s = new FakeSource();
      sources.push(s);
      return s;
    }
    createGain() {
      // The gain param records its scheduled automation so escalation tests can assert
      // on the crossfade ramps; setting .value directly still works for the simple loop.
      const ramps = [];
      const g = {
        gain: {
          value: null,
          setValueAtTime(v, t) {
            ramps.push({ type: "set", v, t });
            this.value = v;
          },
          linearRampToValueAtTime(v, t) {
            ramps.push({ type: "ramp", v, t });
            this.value = v;
          },
          cancelScheduledValues(t) {
            ramps.push({ type: "cancel", t });
          },
        },
        ramps,
        connect: (node) => node,
        disconnect() {},
      };
      gains.push(g);
      return g;
    }
  }

  globalThis.AudioContext = FakeCtx;
  globalThis.fetch = async () => {
    fetchCalls++;
    return { arrayBuffer: async () => new ArrayBuffer(8) };
  };

  const mod = await import(`./music.mjs?t=${seq++}`);
  return { ...mod, sources, gains, fetchCalls: () => fetchCalls };
}

test("start() plays a looping source at the requested gain", async () => {
  const { createMusicLoop, sources, gains } = await setup();
  const loop = createMusicLoop("/x.mp3");
  await loop.start(0.3);
  assert.equal(sources.length, 1);
  assert.equal(sources[0].started, true);
  assert.equal(sources[0].loop, true);
  assert.equal(gains.at(-1).gain.value, 0.3);
  assert.equal(loop.live, true);
});

test("start() defaults to the background MUSIC_GAIN", async () => {
  const { createMusicLoop, MUSIC_GAIN, gains } = await setup();
  const loop = createMusicLoop("/x.mp3");
  await loop.start();
  assert.equal(gains.at(-1).gain.value, MUSIC_GAIN);
});

test("stop() halts the source and clears live", async () => {
  const { createMusicLoop, sources } = await setup();
  const loop = createMusicLoop("/x.mp3");
  await loop.start();
  loop.stop();
  assert.equal(sources[0].stopped, true);
  assert.equal(loop.live, false);
});

test("start() restarts from the top: old source stopped, new one started, no re-fetch", async () => {
  const { createMusicLoop, sources, fetchCalls } = await setup();
  const loop = createMusicLoop("/x.mp3");
  await loop.start();
  await loop.start();
  assert.equal(sources.length, 2);
  assert.equal(sources[0].stopped, true);
  assert.equal(sources[1].started, true);
  assert.equal(loop.live, true);
  assert.equal(fetchCalls(), 1); // buffer is decoded once and reused
});

test("two loops share one AudioContext so a single gesture unlocks both", async () => {
  // The crux of the in-game-music bug: the round loop's start() runs from an async
  // socket callback, not a gesture. A shared context (resumed earlier by the menu loop)
  // is what lets it play. Here: one resume across both loops' contexts.
  const { createMusicLoop, sources } = await setup();
  const lobby = createMusicLoop("/lobby.mp3");
  const game = createMusicLoop("/game.mp3");
  await lobby.start();
  await game.start();
  // Both produced a source on the same context (recorded in one shared array).
  assert.equal(sources.length, 2);
  assert.ok(sources.every((s) => s.started));
});

test("setGain re-levels the playing loop", async () => {
  const { createMusicLoop, gains } = await setup();
  const loop = createMusicLoop("/x.mp3");
  await loop.start(0.5);
  loop.setGain(0.2);
  assert.equal(gains.at(-1).gain.value, 0.2);
});

test("setGain before start is a harmless no-op", async () => {
  const { createMusicLoop } = await setup();
  const loop = createMusicLoop("/x.mp3");
  loop.setGain(0.2); // no node yet — must not throw
  assert.equal(loop.live, false);
});

test("start() stays silent when WebAudio is unavailable", async () => {
  const { createMusicLoop } = await setup();
  globalThis.AudioContext = class {
    constructor() {
      throw new Error("no WebAudio");
    }
  };
  const loop = createMusicLoop("/x.mp3");
  await loop.start(); // swallows the error
  assert.equal(loop.live, false);
});

const STAGE_URLS = ["/s1.mp3", "/s2.mp3", "/s3.mp3", "/s4.mp3"];

test("escalating loop plays every stage at once, phase-locked, with only stage 1 audible", async () => {
  const { createEscalatingLoop, sources, gains } = await setup();
  const loop = createEscalatingLoop(STAGE_URLS);
  // escalate:false so the initial per-stage gains aren't immediately overwritten by the
  // scheduled crossfade ramps (the mock collapses scheduled values onto .value).
  await loop.start(0.4, { escalate: false });

  // One looping, started source per stage.
  assert.equal(sources.length, 4);
  assert.ok(sources.every((s) => s.started && s.loop));
  // gains: [master, stage0..stage3]. Master carries the level; only stage 1 is open.
  const [master, ...stageGains] = gains;
  assert.equal(master.gain.value, 0.4);
  assert.equal(stageGains[0].gain.value, 1);
  assert.deepEqual(
    stageGains.slice(1).map((g) => g.gain.value),
    [0, 0, 0],
  );
  assert.equal(loop.live, true);
});

test("escalate (the default) schedules crossfade ramps up the ladder", async () => {
  const { createEscalatingLoop, gains } = await setup();
  const loop = createEscalatingLoop(STAGE_URLS, { stageMs: 15000, crossMs: 1200 });
  await loop.start();

  const stageGains = gains.slice(1);
  // Stage 1 fades out once (its boundary); the middle stages fade in then out; the
  // final stage only fades in — so there is automation on every stage gain.
  assert.ok(stageGains.every((g) => g.ramps.length > 0));
  // First boundary at t0(0)+15s: stage 1 ramps 1→0 and stage 2 ramps 0→1 over 1.2s.
  assert.deepEqual(stageGains[0].ramps, [
    { type: "set", v: 1, t: 15 },
    { type: "ramp", v: 0, t: 16.2 },
  ]);
  assert.deepEqual(stageGains[1].ramps.slice(0, 2), [
    { type: "set", v: 0, t: 15 },
    { type: "ramp", v: 1, t: 16.2 },
  ]);
});

test("escalate:false holds the chill stage-1 bed (no ramps scheduled)", async () => {
  const { createEscalatingLoop, gains } = await setup();
  const loop = createEscalatingLoop(STAGE_URLS);
  await loop.start(undefined, { escalate: false });

  const stageGains = gains.slice(1);
  assert.ok(stageGains.every((g) => g.ramps.length === 0));
  assert.equal(stageGains[0].gain.value, 1); // stage 1 audible and steady
});

test("escalating loop stop() halts every stage and clears live", async () => {
  const { createEscalatingLoop, sources } = await setup();
  const loop = createEscalatingLoop(STAGE_URLS);
  await loop.start();
  loop.stop();
  assert.ok(sources.every((s) => s.stopped));
  assert.equal(loop.live, false);
});

test("escalating loop restart decodes each stage once and reuses the buffers", async () => {
  const { createEscalatingLoop, fetchCalls } = await setup();
  const loop = createEscalatingLoop(STAGE_URLS);
  await loop.start();
  await loop.start();
  assert.equal(fetchCalls(), STAGE_URLS.length); // four stages, fetched once each
});

test("escalating loop setGain re-levels the master", async () => {
  const { createEscalatingLoop, gains } = await setup();
  const loop = createEscalatingLoop(STAGE_URLS);
  await loop.start(0.5);
  loop.setGain(0.2);
  assert.equal(gains[0].gain.value, 0.2); // master is the first gain created
});

// --- fade / restage / wanted (the seamless-transition primitives) ---

test("wanted is true the instant start() is called, before its async decode makes a source", async () => {
  const { createMusicLoop } = await setup();
  const loop = createMusicLoop("/x.mp3");
  const p = loop.start(); // do NOT await — mid-flight, the buffer is still decoding
  assert.equal(loop.wanted, true); // intended-to-play immediately…
  assert.equal(loop.live, false); // …but no source node yet (the home→lobby skip window)
  await p;
  assert.equal(loop.live, true); // now the source exists
});

test("start({fadeMs}) ramps the loop up from silence instead of snapping to gain", async () => {
  const { createMusicLoop, gains } = await setup();
  const loop = createMusicLoop("/x.mp3");
  await loop.start(0.4, { fadeMs: 600 });
  const g = gains.at(-1);
  assert.equal(g.gain.value, 0.4); // ends at the target
  // opened at 0 and ramped to 0.4 at t0(0)+0.6s
  assert.deepEqual(g.ramps, [
    { type: "set", v: 0, t: 0 },
    { type: "ramp", v: 0.4, t: 0.6 },
  ]);
});

test("fadeTo ramps the live loop to a new level without restarting (no new source)", async () => {
  const { createMusicLoop, sources, gains } = await setup();
  const loop = createMusicLoop("/x.mp3");
  await loop.start(0.5);
  loop.fadeTo(0, 600);
  assert.equal(sources.length, 1); // still the one source — no restart
  const r = gains.at(-1).ramps;
  assert.deepEqual(r.at(-1), { type: "ramp", v: 0, t: 0.6 }); // ramped to 0 over 600ms
  assert.equal(r.some((x) => x.type === "cancel"), true); // pending ramps cancelled first
});

test("fadeTo before start is a harmless no-op", async () => {
  const { createMusicLoop } = await setup();
  const loop = createMusicLoop("/x.mp3");
  loop.fadeTo(0.2); // no node yet — must not throw
  assert.equal(loop.live, false);
});

test("escalating fadeTo ramps the master (the between-rounds duck) without restarting", async () => {
  const { createEscalatingLoop, sources, gains } = await setup();
  const loop = createEscalatingLoop(STAGE_URLS);
  await loop.start(0.4, { escalate: false });
  loop.fadeTo(0.13, 600); // duck to the limbo level
  assert.equal(sources.length, 4); // no teardown
  assert.deepEqual(gains[0].ramps.at(-1), { type: "ramp", v: 0.13, t: 0.6 }); // master ramped
});

test("restage resets the ladder IN PLACE — same sources, climb re-scheduled, no phase reset", async () => {
  const { createEscalatingLoop, sources, gains } = await setup();
  const loop = createEscalatingLoop(STAGE_URLS);
  await loop.start(0.4, { escalate: false }); // sitting on the stage-1 bed
  const before = sources.length;

  loop.restage({ escalate: true }); // back to a climbing round, in place

  assert.equal(sources.length, before); // NO new sources — the four keep running, phase intact
  assert.ok(sources.every((s) => !s.stopped)); // nothing was torn down
  // Every stage gain was reset (crossfaded back toward stage 1) and the climb re-scheduled.
  const stageGains = gains.slice(1);
  assert.ok(stageGains.every((g) => g.ramps.some((r) => r.type === "cancel")));
  assert.ok(stageGains.every((g) => g.ramps.some((r) => r.type === "ramp")));
});

test("restage holds the bed when escalate:false (ladder reset, no climb beyond the reset)", async () => {
  const { createEscalatingLoop, gains } = await setup();
  const loop = createEscalatingLoop(STAGE_URLS, { stageMs: 15000, crossMs: 1200 });
  await loop.start(0.4); // a climbing round (ramps scheduled)
  gains.forEach((g) => (g.ramps.length = 0)); // focus on what restage does

  loop.restage({ escalate: false }); // drop to the chill bed and hold

  const stageGains = gains.slice(1);
  // Stage 1 is brought back up; every stage's only ramp target is the reset (no boundary climbs).
  assert.deepEqual(stageGains[0].ramps.filter((r) => r.type === "ramp"), [{ type: "ramp", v: 1, t: 1.2 }]);
  assert.deepEqual(stageGains[1].ramps.filter((r) => r.type === "ramp"), [{ type: "ramp", v: 0, t: 1.2 }]);
});

test("restage before start is a harmless no-op", async () => {
  const { createEscalatingLoop, sources } = await setup();
  const loop = createEscalatingLoop(STAGE_URLS);
  loop.restage({ escalate: true }); // no master yet — must not throw
  assert.equal(sources.length, 0);
});
