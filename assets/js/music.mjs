// Gapless looping background music via WebAudio. decodeAudioData yields PCM with none
// of the mp3 encoder padding that makes an `<audio loop>` click on repeat, so the loop
// is seamless from the mp3 alone (see priv/static/sounds/music/README.md).
//
// Browser autoplay policy means start() must be called from a user gesture. suspend()/
// resume() pause and continue the context, preserving the playhead — so toggling music
// across, say, lobby↔round is seamless within a session. (Crossing a full page load is
// not: that tears down the context and re-arms the autoplay block.)

// Background level — kept low so the bullet/footstep SFX cut through (music/README.md
// suggests ~0.4–0.5). master volume scales this further.
export const MUSIC_GAIN = 0.45;

export function createMusicLoop(url) {
  let ctx = null;
  let gainNode = null;
  let starting = false;
  let live = false;

  return {
    async start(gain = 0.45) {
      if (live || starting) return;
      starting = true;
      try {
        ctx = new AudioContext();
        const res = await fetch(url);
        const buf = await ctx.decodeAudioData(await res.arrayBuffer());
        const src = ctx.createBufferSource();
        src.buffer = buf;
        src.loop = true;
        gainNode = ctx.createGain();
        gainNode.gain.value = gain;
        src.connect(gainNode).connect(ctx.destination);
        src.start();
        live = true;
      } catch {
        /* WebAudio unavailable or fetch failed — caller just stays silent */
      } finally {
        starting = false;
      }
    },
    setGain(gain) {
      if (gainNode) gainNode.gain.value = gain;
    },
    suspend() {
      ctx?.suspend();
    },
    resume() {
      ctx?.resume();
    },
    get live() {
      return live;
    },
  };
}
