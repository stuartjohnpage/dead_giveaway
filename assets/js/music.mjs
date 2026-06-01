// Gapless looping background music via WebAudio. decodeAudioData yields PCM with none
// of the mp3 encoder padding that makes an `<audio loop>` click on repeat, so the loop
// is seamless from the mp3 alone (see priv/static/sounds/music/README.md).
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

export function createMusicLoop(url) {
  let buffer = null; // decoded once, reused across restarts
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
