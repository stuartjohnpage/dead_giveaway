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
      const g = { gain: { value: null }, connect: (node) => node };
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
