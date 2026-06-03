// Gapless looping background music via WebAudio. decodeAudioData yields PCM with none
// of the mp3 encoder padding that makes an `<audio loop>` click on repeat, so the loop
// is seamless from the mp3 alone (see tools/asset-gen/MUSIC.md).
//
// Browser autoplay policy means start() must first run from a user gesture. start()
// (re)starts the loop from the top, so moving between views (lobby↔round) simply stops
// one loop and starts the other fresh — no playhead to preserve, no suspend/resume
// juggling. The decoded buffer is cached, so restarting is cheap (no re-fetch/decode).

// Background level — kept low so the bullet/footstep SFX cut through (music/README.md
// suggests ~0.4–0.5). master volume scales this further.
export const MUSIC_GAIN = 0.45;

// One AudioContext shared by every loop on the page. Browsers gate audio behind a user
// gesture: a context is born "suspended" and only a resume() originating from a gesture
// starts it. Sharing a single context means one gesture (e.g. the Go click) unlocks
// *all* loops — crucially the in-game loop, whose start() fires from an async socket
// callback (the round snapshot) long after the gesture's call stack is gone. With a
// context per loop, the game loop's own context never saw a gesture and stayed silent.
let sharedCtx = null;
function audioContext() {
  return (sharedCtx ||= new AudioContext());
}

// True once the shared context is actually producing sound — i.e. autoplay was permitted
// (high media-engagement) or a gesture has already unlocked it. This distinguishes "audio
// is already playing" from "a loop is queued but the context is still suspended (silent),
// awaiting a gesture". Callers use it so the unlock gesture only (re)starts a loop that
// hasn't sounded yet, instead of restarting one that's already playing from the top.
export function audioRunning() {
  return sharedCtx?.state === "running";
}

export function createMusicLoop(url) {
  let buffer = null; // decoded once, reused across restarts (invalidated by setUrl)
  let src = null; // the currently-playing source node (null = stopped)
  let gainNode = null;
  let gain = MUSIC_GAIN;
  let wantPlaying = false; // guards against an in-flight start() racing a stop()

  return {
    // (Re)start the loop from the beginning. Idempotent enough to call on every view
    // change — it tears down any current source first. Must originate from a user
    // gesture the first time, or the AudioContext stays suspended (silent).
    async start(g = MUSIC_GAIN) {
      gain = g;
      wantPlaying = true;
      try {
        const ctx = audioContext();
        if (!buffer) {
          const res = await fetch(url);
          buffer = await ctx.decodeAudioData(await res.arrayBuffer());
        }
        await ctx.resume(); // a no-op until the first gesture; resumes a suspended ctx after
        if (!wantPlaying) return; // stopped while we were fetching/decoding
        if (src) {
          try {
            src.stop();
          } catch {
            /* already stopped */
          }
          src.disconnect();
        }
        src = ctx.createBufferSource();
        src.buffer = buffer;
        src.loop = true;
        gainNode = ctx.createGain();
        gainNode.gain.value = gain;
        src.connect(gainNode).connect(ctx.destination);
        src.start();
      } catch {
        /* WebAudio unavailable or fetch failed — caller just stays silent */
      }
    },
    setGain(g) {
      gain = g;
      if (gainNode) gainNode.gain.value = g;
    },
    // Retarget the loop at a different track (e.g. a theme swap). Drops the cached
    // buffer so the next start() re-fetches/decodes; the caller restarts to hear it.
    setUrl(u) {
      url = u;
      buffer = null;
    },
    stop() {
      wantPlaying = false;
      if (src) {
        try {
          src.stop();
        } catch {
          /* already stopped */
        }
        src.disconnect();
        src = null;
      }
    },
    get live() {
      return !!src;
    },
  };
}

// The in-game music advances one stage every 15s, then holds at the top (game README).
export const STAGE_MS = 15_000;
// Crossfade length at each stage boundary. The stages share key/tempo/length, so a
// linear gain crossfade mid-loop still lands musically.
const CROSS_MS = 1200;

// A four-stage escalating loop with the SAME shape as createMusicLoop (start/stop/
// setGain/live), so callers swap it in without changing their control flow.
//
// All stages are equal-length loops on one grid, so we start every stage source
// together (phase-locked for the loop's whole life) and treat escalation as pure gain
// automation — fade the next stage up and the current one down at each boundary, with
// no playhead to align. `start({escalate})` false holds at stage 1 (the chill bed, for
// the between-rounds card); true climbs the ladder and holds at the final stage.
export function createEscalatingLoop(urls, { stageMs = STAGE_MS, crossMs = CROSS_MS } = {}) {
  let buffers = null; // decoded once, reused across restarts (invalidated by setUrls)
  let sources = []; // current per-stage source nodes ([] = stopped)
  let stageGains = []; // per-stage gain nodes we automate to crossfade
  let master = null; // master gain (carries the volume level)
  let gain = MUSIC_GAIN;
  let wantPlaying = false;

  const fade = (param, from, to, at, dur) => {
    param.setValueAtTime(from, at);
    param.linearRampToValueAtTime(to, at + dur);
  };

  const teardown = () => {
    for (const s of sources) {
      try {
        s.stop();
      } catch {
        /* already stopped */
      }
      s.disconnect();
    }
    for (const sg of stageGains) sg.disconnect();
    if (master) master.disconnect();
    sources = [];
    stageGains = [];
    master = null;
  };

  return {
    // (Re)start at stage 1. `escalate` true schedules the climb (one stage per stageMs,
    // holding at the last); false holds at the chill bed. Like createMusicLoop.start,
    // must first run from a user gesture or the shared AudioContext stays suspended.
    async start(g = MUSIC_GAIN, { escalate = true } = {}) {
      gain = g;
      wantPlaying = true;
      try {
        const ctx = audioContext();
        if (!buffers) {
          buffers = await Promise.all(
            urls.map(async (u) => ctx.decodeAudioData(await (await fetch(u)).arrayBuffer())),
          );
        }
        await ctx.resume(); // no-op until the first gesture; resumes a suspended ctx after
        if (!wantPlaying) return; // stopped while we were fetching/decoding
        teardown();

        master = ctx.createGain();
        master.gain.value = gain;
        master.connect(ctx.destination);

        const t0 = ctx.currentTime;
        buffers.forEach((buf, i) => {
          const sg = ctx.createGain();
          sg.gain.value = i === 0 ? 1 : 0; // stage 1 audible, the rest silent
          sg.connect(master);
          const s = ctx.createBufferSource();
          s.buffer = buf;
          s.loop = true;
          s.connect(sg);
          s.start(t0); // start every stage together so they stay phase-locked
          sources.push(s);
          stageGains.push(sg);
        });

        // Climb the ladder: at each boundary fade the next stage in and the current out.
        // Past the last boundary there are no more ramps, so it simply holds at the top.
        if (escalate) {
          const dur = crossMs / 1000;
          for (let i = 1; i < buffers.length; i++) {
            const at = t0 + (i * stageMs) / 1000;
            fade(stageGains[i - 1].gain, 1, 0, at, dur);
            fade(stageGains[i].gain, 0, 1, at, dur);
          }
        }
      } catch {
        /* WebAudio unavailable or fetch failed — caller just stays silent */
      }
    },
    setGain(g) {
      gain = g;
      if (master) master.gain.value = g;
    },
    // Retarget at a different set of stage tracks (a theme swap). Drops the cached
    // buffers so the next start() re-fetches/decodes; the caller restarts to hear it.
    setUrls(us) {
      urls = us;
      buffers = null;
    },
    stop() {
      wantPlaying = false;
      teardown();
    },
    get live() {
      return sources.length > 0;
    },
  };
}
