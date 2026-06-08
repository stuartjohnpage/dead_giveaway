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

// Default crossfade/duck length for view transitions. Long enough to read as a
// deliberate blend (not a cut), short enough not to drag. Used by the loops' fadeTo and
// by the music director's adapter (lobby↔game crossfade, between-rounds duck).
export const FADE_MS = 900;
// The between-rounds "limbo" level: the game loop ducks to this fraction of its normal
// gain on the card, so the round's end reads as a breath without going fully silent.
export const DUCK_LEVEL = 0.32;

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
    // gesture the first time, or the AudioContext stays suspended (silent). Pass
    // `fadeMs` to ramp up from silence instead of snapping to `g` (a crossfade-in).
    async start(g = MUSIC_GAIN, { fadeMs = 0 } = {}) {
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
        gainNode.gain.value = fadeMs ? 0 : gain;
        src.connect(gainNode).connect(ctx.destination);
        src.start();
        if (fadeMs) {
          const t0 = ctx.currentTime;
          gainNode.gain.setValueAtTime(0, t0);
          gainNode.gain.linearRampToValueAtTime(gain, t0 + fadeMs / 1000);
        }
      } catch {
        /* WebAudio unavailable or fetch failed — caller just stays silent */
      }
    },
    setGain(g) {
      gain = g;
      if (gainNode) gainNode.gain.value = g;
    },
    // Ramp the live loop to `level` over `ms` (a crossfade/duck), leaving it playing. A
    // no-op on a loop that has never started (no node yet) — the caller passes fadeMs to
    // start() instead for the fade-IN. Doesn't touch the stored `gain`, so a later
    // setGain still restores the nominal level.
    fadeTo(level, ms = FADE_MS) {
      if (!gainNode) return;
      const ctx = audioContext();
      const t0 = ctx.currentTime;
      const p = gainNode.gain;
      p.cancelScheduledValues(t0);
      p.setValueAtTime(p.value, t0);
      p.linearRampToValueAtTime(level, t0 + ms / 1000);
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
    // "Intended to be playing" — true from the moment start() is called, BEFORE its async
    // fetch/decode has created the source node. The "adopt vs (re)start" decision keys off
    // this rather than `live`: when the first gesture is the navigation click itself,
    // start()'s buffer is still decoding when the next page boots, so a `live`-based check
    // would see no source and issue a SECOND start() — restarting the loop from the top
    // just as the new view appears (the home→lobby skip).
    get wanted() {
      return wantPlaying;
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

  // Schedule the climb up the ladder starting at `base`: at each stage boundary fade the
  // next stage in and the current out. Past the last boundary there are no more ramps, so
  // it simply holds at the top. Shared by start() (climb from t0) and restage() (climb
  // from the reset point).
  const scheduleClimb = (base) => {
    const dur = crossMs / 1000;
    for (let i = 1; i < stageGains.length; i++) {
      const at = base + (i * stageMs) / 1000;
      fade(stageGains[i - 1].gain, 1, 0, at, dur);
      fade(stageGains[i].gain, 0, 1, at, dur);
    }
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
    // holding at the last); false holds at the chill bed. `fadeMs` ramps the master up
    // from silence (a crossfade-in) instead of snapping to `g`. Like createMusicLoop.start,
    // must first run from a user gesture or the shared AudioContext stays suspended.
    //
    // NB: this tears the loop down and restarts it (resetting the loop phase). The normal
    // round→card→round flow uses restage() instead, which keeps the sources running so the
    // beat never breaks; start() is for first playback, a theme swap, or coming back from
    // a fully-stopped (e.g. page-loaded-muted) loop.
    async start(g = MUSIC_GAIN, { escalate = true, fadeMs = 0 } = {}) {
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
        master.gain.value = fadeMs ? 0 : gain;
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
        if (escalate) scheduleClimb(t0);
        if (fadeMs) {
          master.gain.setValueAtTime(0, t0);
          master.gain.linearRampToValueAtTime(gain, t0 + fadeMs / 1000);
        }
      } catch {
        /* WebAudio unavailable or fetch failed — caller just stays silent */
      }
    },
    setGain(g) {
      gain = g;
      if (master) master.gain.value = g;
    },
    // Ramp the master to `level` over `ms` (the between-rounds duck, or a crossfade in/out)
    // without restarting — the stages keep playing, phase intact. No-op before first start.
    fadeTo(level, ms = FADE_MS) {
      if (!master) return;
      const ctx = audioContext();
      const t0 = ctx.currentTime;
      const p = master.gain;
      p.cancelScheduledValues(t0);
      p.setValueAtTime(p.value, t0);
      p.linearRampToValueAtTime(level, t0 + ms / 1000);
    },
    // Reset the stage ladder back to stage 1 *in place* — the four sources keep running
    // phase-locked, so unlike start() there's no teardown and no phase reset (the beat
    // carries unbroken across a round boundary). Crossfades the ladder down to the stage-1
    // bed; `escalate` true then re-schedules the climb. A no-op if not yet started (the
    // caller falls back to start() for that). This is what makes round→card→round seamless.
    restage({ escalate = true } = {}) {
      if (!master) return;
      const ctx = audioContext();
      const t0 = ctx.currentTime;
      const dur = crossMs / 1000;
      // Crossfade every stage back to the stage-1 bed (stage 0 up, the rest down), first
      // cancelling any climb ramps still pending from the previous round.
      stageGains.forEach((sg, i) => {
        const p = sg.gain;
        p.cancelScheduledValues(t0);
        p.setValueAtTime(p.value, t0);
        p.linearRampToValueAtTime(i === 0 ? 1 : 0, t0 + dur);
      });
      // Climb again from the reset point (past the short crossfade), if asked.
      if (escalate) scheduleClimb(t0 + dur);
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
    // Intended-to-be-playing, set before start()'s async decode produces the sources — see
    // the note on createMusicLoop's `wanted`.
    get wanted() {
      return wantPlaying;
    },
  };
}
