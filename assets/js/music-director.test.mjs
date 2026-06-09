import { test } from "node:test";
import assert from "node:assert/strict";

import { createMusicDirector, createAudioPort } from "./music-director.mjs";
import { FADE_MS, DUCK_LEVEL } from "./music.mjs";

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
    enters: () => calls.filter((c) => c.op === "enterRound" || c.op === "enterCard"),
    play: (name, opts) => calls.push({ op: "play", name, ...opts }),
    enterRound: (opts) => calls.push({ op: "enterRound", ...opts }),
    enterCard: (opts) => calls.push({ op: "enterCard", ...opts }),
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

test("adoptLobby takes the lobby view WITHOUT replaying (the carried-over splash loop)", () => {
  const audio = fakeAudio();
  const music = createMusicDirector(audio);
  music.adoptLobby();
  // No play: the menu loop is already sounding (started on the splash) and must not restart.
  assert.deepEqual(audio.plays(), []);
  assert.equal(music.inGame, false);

  // It still set the replay target to the lobby loop: an unlock gesture (suspended ctx)
  // now (re)plays the lobby, exactly as a toLobby would have.
  assert.equal(music.prime(), true);
  assert.deepEqual(audio.plays(), [{ op: "play", name: "lobby", gain: 0.4 }]);
});

test("after adoptLobby, the first round crossfades in from the lobby (fromLobby:true)", () => {
  const audio = fakeAudio();
  const music = createMusicDirector(audio);
  music.adoptLobby();
  music.toRound();
  assert.deepEqual(audio.enters(), [
    { op: "enterRound", gain: 0.4, escalate: true, fromLobby: true },
  ]);
  assert.equal(music.inGame, true);
});

test("a snapshot before round_start enters the round exactly once (idempotent ensureInGame)", () => {
  const audio = fakeAudio();
  const music = createMusicDirector(audio);
  music.toLobby();
  music.ensureInGame(); // stray snapshot beats round_start → enter the round (from the lobby)
  music.ensureInGame(); // second stray snapshot → no-op
  assert.deepEqual(audio.plays(), [{ op: "play", name: "lobby", gain: 0.4 }]);
  assert.deepEqual(audio.enters(), [
    { op: "enterRound", gain: 0.4, escalate: true, fromLobby: true },
  ]);
  assert.equal(music.inGame, true);
});

test("once in-game, no transition ever returns to the menu loop", () => {
  const audio = fakeAudio();
  const music = createMusicDirector(audio);
  music.toLobby();
  music.toRound();
  music.toCard();
  music.ensureInGame();
  // Only the first (pre-game) play targets the lobby; everything after is an in-game enter.
  const lobbyPlaysAfterFirst = audio.plays().slice(1).filter((c) => c.name === "lobby");
  assert.deepEqual(lobbyPlaysAfterFirst, []);
  // The first round crossfades from the lobby; the card never does (it's already in-game).
  assert.deepEqual(audio.enters(), [
    { op: "enterRound", gain: 0.4, escalate: true, fromLobby: true },
    { op: "enterCard", gain: 0.4 },
  ]);
  assert.equal(music.inGame, true);
});

test("round_start enters climbing; round_over ducks to the card; the climb-back is in place (fromLobby:false)", () => {
  const audio = fakeAudio();
  const music = createMusicDirector(audio);
  music.toRound(); // first round: crossfade in from the (null) lobby
  music.toCard(); // round over: duck to the bed
  music.toRound(); // play again: NOT from the lobby — restage in place
  assert.deepEqual(audio.enters(), [
    { op: "enterRound", gain: 0.4, escalate: true, fromLobby: true },
    { op: "enterCard", gain: 0.4 },
    { op: "enterRound", gain: 0.4, escalate: true, fromLobby: false },
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

test("re-setting the SAME theme is a no-op — no retarget, no replay (the singleton survives nav)", () => {
  const audio = fakeAudio();
  const music = createMusicDirector(audio);
  music.setTheme({ menuLoop: "/m.mp3", gameStages: ["/g1.mp3", "/g2.mp3"] }); // first page boot
  music.adoptLobby(); // menu loop carried over and playing
  audio.calls.length = 0; // focus on the redundant re-set

  // A second lobby's boot reloads the SAME default theme. The director outlives the page, so
  // `themed` is already true — but the tracks are unchanged, so it must touch nothing (no
  // retarget that drops the buffer, no replay that restarts the loop). This is the home→lobby
  // skip-on-the-second-lobby bug: the carry stays seamless only if this is a true no-op.
  music.setTheme({ menuLoop: "/m.mp3", gameStages: ["/g1.mp3", "/g2.mp3"] });
  assert.deepEqual(audio.calls, []);
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
  // The director faithfully passes the current gain; a gain-0 enter is the adapter's cue
  // to keep things silent — the gain>0 guards are exercised directly below.
  assert.deepEqual(audio.enters(), [
    { op: "enterRound", gain: 0.4, escalate: true, fromLobby: true },
    { op: "enterCard", gain: 0 },
  ]);
});

// --- The production AudioPort adapter (createAudioPort) over fake loops ---

// Record start/stop/setUrl(s)/fadeTo/restage on a fake loop so we can assert the adapter's
// mechanics. `live` reflects whether a source is currently running (set at construction).
function fakeLoop({ live = false } = {}) {
  const calls = [];
  return {
    calls,
    start: (g, opts) => calls.push({ op: "start", g, ...(opts || {}) }),
    stop: () => calls.push({ op: "stop" }),
    setUrl: (u) => calls.push({ op: "setUrl", u }),
    setUrls: (u) => calls.push({ op: "setUrls", u }),
    fadeTo: (level, ms) => calls.push({ op: "fadeTo", level, ms }),
    restage: (opts) => calls.push({ op: "restage", ...(opts || {}) }),
    get live() {
      return live;
    },
  };
}

function fakePort({ gain = 0.4, running = false, gameLive = false } = {}) {
  const lobbyMusic = fakeLoop();
  const gameMusic = fakeLoop({ live: gameLive });
  const port = createAudioPort({ lobbyMusic, gameMusic, audioRunning: () => running, gain: () => gain });
  return { port, lobbyMusic, gameMusic };
}


test("adapter: play('lobby') stops game music and starts lobby at the given gain", () => {
  const { port, lobbyMusic, gameMusic } = fakePort();
  port.play("lobby", { gain: 0.4 });
  assert.deepEqual(gameMusic.calls, [{ op: "stop" }]);
  assert.deepEqual(lobbyMusic.calls, [{ op: "start", g: 0.4 }]);
});

test("adapter: play('game') stops lobby music and starts game with escalate", () => {
  const { port, lobbyMusic, gameMusic } = fakePort();
  port.play("game", { gain: 0.4, escalate: true });
  assert.deepEqual(lobbyMusic.calls, [{ op: "stop" }]);
  assert.deepEqual(gameMusic.calls, [{ op: "start", g: 0.4, escalate: true }]);
});

test("adapter: a gain-0 play still stops the other loop but starts nothing (silence guard)", () => {
  const { port, lobbyMusic, gameMusic } = fakePort();
  port.play("lobby", { gain: 0 });
  // The other loop is always stopped; the muted loop is not started.
  assert.deepEqual(gameMusic.calls, [{ op: "stop" }]);
  assert.deepEqual(lobbyMusic.calls, []);

  port.play("game", { gain: 0, escalate: true });
  assert.deepEqual(lobbyMusic.calls, [{ op: "stop" }]);
  assert.deepEqual(gameMusic.calls, [{ op: "stop" }]); // stop from the lobby play above only
});

test("adapter: retarget points the named loop at new track(s) without starting it", () => {
  const { port, lobbyMusic, gameMusic } = fakePort();
  port.retarget("lobby", "/m.mp3");
  port.retarget("game", ["/g1.mp3", "/g2.mp3"]);
  assert.deepEqual(lobbyMusic.calls, [{ op: "setUrl", u: "/m.mp3" }]);
  assert.deepEqual(gameMusic.calls, [{ op: "setUrls", u: ["/g1.mp3", "/g2.mp3"] }]);
});

test("adapter: gain and audioRunning pass through to the injected getters", () => {
  const { port } = fakePort({ gain: 0.25, running: true });
  assert.equal(port.gain(), 0.25);
  assert.equal(port.audioRunning(), true);
});

test("adapter: enterRound(fromLobby) crossfades — ducks the menu loop out, fades the game in", () => {
  const { port, lobbyMusic, gameMusic } = fakePort({ gain: 0.4 });
  port.enterRound({ gain: 0.4, escalate: true, fromLobby: true });
  // Menu loop ducked to silence (left running — not stopped); game loop started with a fade-in.
  assert.deepEqual(lobbyMusic.calls, [{ op: "fadeTo", level: 0, ms: FADE_MS }]);
  assert.deepEqual(gameMusic.calls, [{ op: "start", g: 0.4, escalate: true, fadeMs: FADE_MS }]);
});

test("adapter: enterRound from the card (game live) restages in place — no restart", () => {
  const { port, lobbyMusic, gameMusic } = fakePort({ gain: 0.4, gameLive: true });
  port.enterRound({ gain: 0.4, escalate: true, fromLobby: false });
  assert.deepEqual(lobbyMusic.calls, []); // the menu loop is untouched mid-game
  assert.deepEqual(gameMusic.calls, [
    { op: "restage", escalate: true }, // ladder reset in place…
    { op: "fadeTo", level: 0.4, ms: FADE_MS }, // …un-ducked back to full
  ]);
});

test("adapter: enterRound from a muted round (game NOT live) starts it fresh with a fade-in", () => {
  const { port, gameMusic } = fakePort({ gain: 0.4, gameLive: false });
  port.enterRound({ gain: 0.4, escalate: true, fromLobby: false });
  // Never started (page was muted) → no source to restage, so bring it up cleanly.
  assert.deepEqual(gameMusic.calls, [{ op: "start", g: 0.4, escalate: true, fadeMs: FADE_MS }]);
});

test("adapter: a muted enterRound(fromLobby) ducks the menu out but starts no game loop", () => {
  const { port, lobbyMusic, gameMusic } = fakePort({ gain: 0 });
  port.enterRound({ gain: 0, escalate: true, fromLobby: true });
  assert.deepEqual(lobbyMusic.calls, [{ op: "fadeTo", level: 0, ms: FADE_MS }]);
  assert.deepEqual(gameMusic.calls, []); // gain 0 → nothing sounded
});

test("adapter: enterCard restages to the bed and ducks the game to the limbo level", () => {
  const { port, gameMusic } = fakePort({ gain: 0.4, gameLive: true });
  port.enterCard({ gain: 0.4 });
  assert.deepEqual(gameMusic.calls, [
    { op: "restage", escalate: false }, // hold the chill stage-1 bed…
    { op: "fadeTo", level: 0.4 * DUCK_LEVEL, ms: FADE_MS }, // …ducked to limbo
  ]);
});

test("adapter: a muted enterCard ducks straight to silence", () => {
  const { port, gameMusic } = fakePort({ gain: 0, gameLive: true });
  port.enterCard({ gain: 0 });
  assert.deepEqual(gameMusic.calls, [
    { op: "restage", escalate: false },
    { op: "fadeTo", level: 0, ms: FADE_MS },
  ]);
});
