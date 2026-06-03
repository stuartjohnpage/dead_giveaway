# In-game escalating music

> **Note:** the shipped Neon stage loops live at `priv/static/themes/neon/game/stage1..4.mp3`
> (each theme owns its own in-round music). This `tools/asset-gen/` directory (outside the
> web-served tree) keeps the generator and the raw `stems/`.

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

**Currently wired in:** the full four-stage escalation, via `createEscalatingLoop`
in `music.mjs` (`assets/js/game.mjs`). All four stage loops are decoded and started
together so they stay phase-locked, and escalation is pure gain automation — at each
15s boundary the next stage crossfades in and the current one out (WebAudio
`linearRampToValueAtTime`, gapless), holding at stage 4. A live round opens on stage 1
and climbs; the between-rounds "Play again?" card resets to the stage-1 bed and *holds*
there (no climb), so the next round ramps up from calm again.

The HTML5 two-element crossfade below is the original sketch of the same idea; the
shipped version does it in WebAudio (sample-accurate scheduling, one shared
AudioContext, honours the master sound switch). Future upgrade: drive the stage advance
off the lead racer's progress to the finish rather than wall-clock 15s (see Notes).

## Wiring it (HTML5, two-element crossfade)

Two `<audio>` elements; fade the new stage in while fading the old one out at each 15s
boundary. Because the stages share the grid, fading mid-loop still sounds musical.

```js
const STAGES = [1,2,3,4].map(i => {
  const a = new Audio(`/themes/neon/game/stage${i}.mp3`);
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
python3 tools/asset-gen/gen_game_music.py out/ && \
  for i in 1 2 3 4; do ffmpeg -y -i out/stage$i.wav -b:a 160k stage$i.mp3; done
```
