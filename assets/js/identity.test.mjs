import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";

// identity.mjs is a browser module; give it just enough globals to run under node —
// a Map-backed localStorage and a document with no fields on the page (so the name
// falls back to the remembered value, exactly the off-splash path).
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
};
globalThis.document = { getElementById: () => null };

const { withIdentity, currentLook, rememberLook } = await import("./identity.mjs");

beforeEach(() => store.clear());

test("with nothing remembered the path rides untouched", () => {
  assert.equal(withIdentity("/play/ABCD"), "/play/ABCD");
});

test("a remembered name and look ride as query params — the server-side contract (#67)", () => {
  store.set("dg:name", "Ada");
  rememberLook({ hat: 2, face: 0, body: 5 });

  assert.equal(withIdentity("/play/ABCD"), "/play/ABCD?name=Ada&hat=2&face=0&body=5");
});

test("a look rides alone when no name is set", () => {
  rememberLook({ hat: 1, face: 1, body: 1 });
  assert.equal(withIdentity("/play/new"), "/play/new?hat=1&face=1&body=1");
});

test("the look round-trips through storage", () => {
  rememberLook({ hat: 4, face: 3, body: 0 });
  assert.deepEqual(currentLook(), { hat: 4, face: 3, body: 0 });
});

test("junk in storage reads as no look at all", () => {
  for (const junk of ["not json", '"crown"', '{"hat":1}', '{"hat":-1,"face":0,"body":0}', '{"hat":"x","face":0,"body":0}']) {
    store.set("dg:look", junk);
    assert.equal(currentLook(), null, `expected null for ${junk}`);
  }
});
