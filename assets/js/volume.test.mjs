import { test } from "node:test";
import assert from "node:assert/strict";

// volume.mjs persists through sessionStorage (session-scoped: a fresh visit starts from
// the defaults — sound on, #62);
// give it a minimal in-memory one so the load/save path runs under Node. (The bindings
// touch the DOM and aren't covered here.)
class FakeStorage {
  constructor() {
    this.m = new Map();
  }
  getItem(k) {
    return this.m.has(k) ? this.m.get(k) : null;
  }
  setItem(k, v) {
    this.m.set(k, String(v));
  }
}
globalThis.sessionStorage = new FakeStorage();

const { loadVolume, saveVolume, sfxGain } = await import("./volume.mjs");

test("sound starts on by default", () => {
  globalThis.sessionStorage = new FakeStorage(); // empty store
  assert.deepEqual(loadVolume(), { enabled: true, master: 10, sfx: 70 });
});

test("stored settings merge over the defaults", () => {
  globalThis.sessionStorage = new FakeStorage();
  sessionStorage.setItem("dg:volume", JSON.stringify({ enabled: true, sfx: 40 }));
  // master is absent in the stored blob → falls back to the default.
  assert.deepEqual(loadVolume(), { enabled: true, master: 10, sfx: 40 });
});

test("save then load round-trips", () => {
  globalThis.sessionStorage = new FakeStorage();
  saveVolume({ enabled: true, master: 80, sfx: 50 });
  assert.deepEqual(loadVolume(), { enabled: true, master: 80, sfx: 50 });
});

test("a corrupt stored value falls back to defaults", () => {
  globalThis.sessionStorage = new FakeStorage();
  sessionStorage.setItem("dg:volume", "{not json");
  assert.deepEqual(loadVolume(), { enabled: true, master: 10, sfx: 70 });
});

test("sfxGain is master × sfx when enabled", () => {
  assert.equal(sfxGain({ enabled: true, master: 100, sfx: 70 }), 0.7);
  assert.equal(sfxGain({ enabled: true, master: 50, sfx: 70 }), 0.35);
});

test("sfxGain is muted (0) when sound is off, whatever the sliders say", () => {
  assert.equal(sfxGain({ enabled: false, master: 100, sfx: 70 }), 0);
});
