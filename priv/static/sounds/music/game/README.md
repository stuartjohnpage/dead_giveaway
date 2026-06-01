# In-game escalating music

Neon Concourse, in-round. Four 15-second seamless loops at rising urgency on the same
key/tempo grid (A-minor + phrygian tension, 128 BPM). The game advances one stage every
15s, then **holds at stage 4** — so tension peaks at ~1 minute and sustains. Reset to
stage 1 at the start of each round.

```
stage1 (bed)      pad + sub + soft kick                       0:00–0:15
stage2 (tense)    + hats, rim, driving 8th bass, arp          0:15–0:30
stage3 (urgent)   + four-on-floor kick, backbeat clap         0:30–0:45
stage4 (frantic)  + 16th hats, phrygian stabs, riser, grit    0:45 → loops
```

Verified: every stage loops seamlessly, all sit at ~-12 dBFS (equal loudness, so
crossfades don't jump), and brightness climbs hard across stages (spectral centroid
0.9k → 3.7k → 5.7k → 6.1k Hz). Urgency rises through density/brightness, not volume.

Files: `stage1.mp3`..`stage4.mp3` (the per-stage loops), `demo.mp3` (all four
back-to-back, 60s), `stems/stem0..3.mp3` (raw layers for a future WebAudio live mix).

**Currently wired in:** the client loops `demo.mp3` as a single in-game track
(`assets/js/game.mjs`, via the gapless WebAudio loop in `music.mjs`) — the round opens on
its stage-1 intro and the 60s escalation repeats. The per-stage crossfade below is the
documented upgrade path (drive `gotoStage()` off game state) for when we want the tension
to hold at stage 4 instead of looping back to the bed.

## Wiring it (HTML5, two-element crossfade)

Two `<audio>` elements; fade the new stage in while fading the old one out at each 15s
boundary. Because the stages share the grid, fading mid-loop still sounds musical.

```js
const STAGES = [1,2,3,4].map(i => {
  const a = new Audio(`/sounds/music/game/stage${i}.mp3`);
  a.loop = true; a.volume = 0; a.preload = "auto";
  return a;
});
let cur = -1;

function gotoStage(i, ms = 1200) {            // crossfade to stage i (0-based)
  i = Math.min(i, STAGES.length - 1);
  if (i === cur) return;
  const incoming = STAGES[i], outgoing = STAGES[cur];
  incoming.currentTime = outgoing ? outgoing.currentTime % incoming.duration : 0; // phase-align
  incoming.play();
  const t0 = performance.now(), from = outgoing ? outgoing.volume : 0;
  (function fade(){
    const k = Math.min(1, (performance.now() - t0) / ms);
    incoming.volume = 0.5 * k;                 // bg level ~0.5
    if (outgoing) outgoing.volume = from * (1 - k);
    if (k < 1) requestAnimationFrame(fade);
    else if (outgoing) outgoing.pause();
  })();
  cur = i;
}

// round start:
function startRoundMusic() {
  cur = -1; gotoStage(0, 0);
  // escalate every 15s, capping at stage 4:
  let s = 0;
  const timer = setInterval(() => {
    if (s >= STAGES.length - 1) return;        // held at frantic
    gotoStage(++s);
  }, 15000);
  return () => { clearInterval(timer); STAGES.forEach(a => a.pause()); };  // call on round end
}
```

Phase-aligning `currentTime` keeps the beat from stuttering across the crossfade. Drop
the lobby/menu track when the round starts and bring this in.

## Notes

- **Gapless stage-4 hold:** `loop` on an MP3 has a tiny encoder-padding gap. For a
  perfectly gapless sustain, decode `stage4` via WebAudio and use
  `AudioBufferSourceNode.loop = true` (decoded PCM has no padding). The stems are there if
  you'd rather mix layers live in WebAudio instead of crossfading pre-mixed stages.
- **Tie to game state instead of a timer:** the bots racing the finish are the real
  shot-clock — you could drive `gotoStage()` off "lead character's progress to the finish"
  rather than wall-clock seconds, so the music tracks how close the round is to ending.
- Regenerate/tune in `../gen_game_music.py` (chord `PROG`, `BPM`, per-layer gains).
```
python3 priv/static/sounds/music/gen_game_music.py out/ && \
  for i in 1 2 3 4; do ffmpeg -y -i out/stage$i.wav -b:a 160k stage$i.mp3; done
```
