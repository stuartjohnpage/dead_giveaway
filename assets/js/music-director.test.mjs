import { test } from "node:test";
import assert from "node:assert/strict";

import { createMusicDirector } from "./music-director.mjs";

// An in-memory recording adapter — the entire boundary to WebAudio, faked. Every command
// the director issues is appended to `calls`; the test drives `audioRunning`/`gain`. No
// DOM, no AudioContext, no music.mjs (mirrors the recording-double idiom in music.test.mjs).
function fakeAudio({ running = false, gain = 0.4 } = {}) {
  const calls = [];
  let _running = running;
  let _gain = gain;
  return {
    calls,
    setRunning: (v) => (_running = v),
    setGain: (v) => (_gain = v),
    plays: () => calls.filter((c) => c.op === "play"),
    play: (name, opts) => calls.push({ op: "play", name, ...opts }),
    retarget: (name, urls) => calls.push({ op: "retarget", name, urls }),
    gain: () => _gain,
    audioRunning: () => _running,
  };
}

test("toLobby starts the lobby loop at the current gain", () => {
  const audio = fakeAudio();
  const music = createMusicDirector(audio);
  music.toLobby();
  assert.deepEqual(audio.plays(), [{ op: "play", name: "lobby", gain: 0.4 }]);
  assert.equal(music.inGame, false);
});

test("a snapshot before round_start starts the game loop exactly once (idempotent ensureInGame)", () => {
  const audio = fakeAudio();
  const music = createMusicDirector(audio);
  music.toLobby();
  music.ensureInGame(); // stray snapshot beats round_start → start game music
  music.ensureInGame(); // second stray snapshot → no-op
  assert.deepEqual(audio.plays(), [
    { op: "play", name: "lobby", gain: 0.4 },
    { op: "play", name: "game", gain: 0.4, escalate: true },
  ]);
  assert.equal(music.inGame, true);
});

test("once in-game, no transition ever issues a lobby play (never back to the menu loop)", () => {
  const audio = fakeAudio();
  const music = createMusicDirector(audio);
  music.toLobby();
  music.toRound();
  music.toCard();
  music.ensureInGame();
  // Only the first (pre-game) play targets the lobby; everything after is the game loop.
  const lobbyPlaysAfterFirst = audio.plays().slice(1).filter((c) => c.name === "lobby");
  assert.deepEqual(lobbyPlaysAfterFirst, []);
  assert.equal(music.inGame, true);
});

test("round_start climbs (escalate:true); round_over holds the chill bed (escalate:false)", () => {
  const audio = fakeAudio();
  const music = createMusicDirector(audio);
  music.toRound();
  music.toCard();
  assert.deepEqual(audio.plays(), [
    { op: "play", name: "game", gain: 0.4, escalate: true },
    { op: "play", name: "game", gain: 0.4, escalate: false },
  ]);
});

test("prime() replays only while suspended and only once across two gestures", () => {
  const audio = fakeAudio({ running: false });
  const music = createMusicDirector(audio);
  music.toLobby(); // one play so far; replay target = lobby
  assert.equal(audio.plays().length, 1);

  // First gesture, context suspended → consumes (true) and replays the lobby loop.
  assert.equal(music.prime(), true);
  assert.equal(audio.plays().length, 2);
  // Second gesture → already primed, returns false and replays nothing.
  assert.equal(music.prime(), false);
  assert.equal(audio.plays().length, 2);
});

test("prime() while the context is already running consumes the gesture but does not replay", () => {
  const audio = fakeAudio({ running: true });
  const music = createMusicDirector(audio);
  music.toLobby();
  assert.equal(audio.plays().length, 1);

  // Autoplay was permitted (already sounding) — the first gesture must not restart it,
  // but still consumes (so the caller removes its listeners).
  assert.equal(music.prime(), true);
  assert.equal(audio.plays().length, 1);
});

test("the boot-time setTheme only retargets — no play", () => {
  const audio = fakeAudio();
  const music = createMusicDirector(audio);
  music.setTheme({ menuLoop: "/m.mp3", gameStages: ["/g1.mp3", "/g2.mp3"] });
  assert.deepEqual(audio.calls, [
    { op: "retarget", name: "lobby", urls: "/m.mp3" },
    { op: "retarget", name: "game", urls: ["/g1.mp3", "/g2.mp3"] },
  ]);
  assert.deepEqual(audio.plays(), []);
});

test("a live setTheme after a round restarts the currently-playing loop", () => {
  const audio = fakeAudio();
  const music = createMusicDirector(audio);
  music.setTheme({ menuLoop: "/m1.mp3", gameStages: ["/a.mp3"] }); // boot load
  music.toRound(); // now in-game, replay = game(escalate:true)
  audio.calls.length = 0; // focus on the live swap

  music.setTheme({ menuLoop: "/m2.mp3", gameStages: ["/b.mp3"] });
  assert.deepEqual(audio.calls, [
    { op: "retarget", name: "lobby", urls: "/m2.mp3" },
    { op: "retarget", name: "game", urls: ["/b.mp3"] },
    // …then a replay of whatever was playing — the climbing game loop.
    { op: "play", name: "game", gain: 0.4, escalate: true },
  ]);
});

test("gain is read fresh per transition, so a mid-game mute lands and the adapter stays silent", () => {
  const audio = fakeAudio({ gain: 0.4 });
  const music = createMusicDirector(audio);
  music.toRound();
  audio.setGain(0); // master muted between transitions
  music.toCard();
  // The director faithfully passes the current gain; a gain-0 play is the adapter's cue
  // to issue nothing (asserted against the production adapter / the gain>0 contract).
  assert.deepEqual(audio.plays(), [
    { op: "play", name: "game", gain: 0.4, escalate: true },
    { op: "play", name: "game", gain: 0, escalate: false },
  ]);
});
