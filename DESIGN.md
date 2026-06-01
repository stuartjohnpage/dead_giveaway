# Dead Giveaway — Design Spec (v1.0)

A browser-based multiplayer hidden-identity game with an Elixir backend, inspired by
the "Death Race" mode from *Hidden in Plain Sight*. Hide among AI characters in a
crowd, blend in, and be the first to cross the finish — without getting picked off by
the other humans hiding alongside you.

> Reference: the original HiPS Death Race (top-down, a scatter of figures, visible
> reticles). We borrow the *gameplay layout only* — **not** the art style.

---

## 1. The fantasy

~30 characters (more with more players) move left → right across a single top-down
room. Any number of them are secretly human; the rest are AI. To a watcher, everyone
looks the same. Win by reaching the finish line first while staying indistinguishable
from the AI crowd — and use your single bullet wisely on whoever you think is human.

## 2. The core twist — hidden identity

- **At spawn you do not know which character is you.**
- Your inputs drive your real character from the first frame; you must **deduce which
  one it is** by moving and watching who responds.
- You are **never marked**. The whole round, you only know yourself by behavior.
- Probing to find yourself is the single most human-looking thing you can do — so the
  opening seconds are when you are most exposed.

## 3. Movement

- **One axis: RIGHT only.** No up, no down, no left, no backward.
- Verbs: **stop / walk-right / run-right**.
- **Controls:** hold to walk, hold **Shift** to run, release to stop. Mouse aims;
  click fires. Rapid tapping = the near-useless "jitter" panic-dodge.
- **Run is faster than any bot ever moves. Bots cannot run.** So *running is always an
  unmistakable human tell* — a pure last resort.
- Pace / being at the front of the pack is a *soft, fuzzy* tell, not a hard one.

## 4. The crowd (bots)

- Headcount scales with players (~6 bots per human, cap ~100). MVP target ~30.
- Characters are scattered at fixed vertical rows and draw from a **shared pool of ~12
  cosmetic sprite variants** (each with idle / walk / run animations). The variant is
  assigned **randomly per character at spawn, server-side, and is NEVER correlated with
  who is human** — it is pure decoration so the crowd reads as a crowd, not a row of
  clones. The same variant can be a human in one round and a bot in the next; cosmetics
  leak no identity. Per-theme art lives in `priv/static/images/themes/<theme>/`.
- Each bot independently **moves or stops in alternating phases**, the duration of each
  phase re-rolled per cycle on its own timing — so the crowd is desynced (no "waves") with
  no mid-phase jitter. A moving bot moves at **exactly the human walk speed**, so pace
  never distinguishes a walking human from a moving bot; only *running* (which no bot can
  do) is a hard tell. Longer stop phases keep overall progress in check.
- Bots **race toward the finish** (they can and do cross it).
- **No bot "noise" for v1** (no fake flinches/pauses/etc.). A `botNoise` dial may be
  added later to introduce false positives.

## 5. Crosshairs & the bullet

- **Everyone sees every crosshair.** Each player has a visible floating reticle.
- You find **your own** crosshair at the start by **moving the mouse**.
- A crosshair is **decoupled from any character body** — seeing a reticle does NOT tell
  you which character its owner is. But *where* a reticle hovers is intel (a reticle
  parked on someone = that someone is suspected).
- **One bullet per player per round.** Hitscan: kills the character **nearest to the
  crosshair**.
- **Firing reveals nothing about who fired.** Its only costs:
  1. You've spent your one and only shot (now defenseless), and
  2. **Your crosshair disappears** — so everyone can see you are now unarmed.
- A kill **reveals nothing** — not who fired, and *not whether you hit a human or a bot*.
  The body simply drops (it ghosts in place); you never learn if the shot was "worth it."
  Every shot is a pure gamble. *(Revised from v1.0, which announced human-vs-bot on a kill
  — that was wrong: it handed everyone free information and gutted the tension.)*
- **You can shoot yourself** — and might, before you know who you are.
- Wasting your shot on a bot leaves you defenseless for the rest of the round.

## 6. The tells (what betrays a human)

- **Running** — always human (bots can't run). The loudest tell.
- **Pace / leading the pack** — soft, fuzzy read.
- **Startle / flinch** — *pure player discipline*; the game forces nothing. Reacting
  (a stutter-stop) when a nearby character is shot gives you away.
- **Discovery-probing** — twitching to find yourself early.
- **Crosshair behavior** — a reticle tracking a specific character, lingering, etc.

## 7. Round flow

- **First character to cross the finish line ends the round** — player **or** bot.
  - Human first → that human **wins (+1)**.
  - **Bot first → the shared "Bot" opponent scores (+1)** and the round resets. No
    human wins, and nothing is persisted to player stats — but the Bot sits on the
    session scoreboard like any player, so the crowd beating you is visible rather
    than a silent "wash". (Bots reaching the line are still the natural shot-clock /
    anti-stalemate — no timer needed, no scroll.)
- Getting shot (or shooting yourself) = **out for the round**, spectate; the round
  continues until someone crosses.

## 8. Session / match structure

- **Endless rounds** with a between-rounds **lobby**: a finish drops everyone out and shows
  the standings; the next round only starts once **≥ 2 players opt back in** ("Play again").
  Players join/leave freely.
- **Cumulative scoreboard** across the session. **Wins only score** (kills are tactics,
  not points).
- A round needs **≥ 2 humans** to start; mid-round joiners **spectate until next round**.
- Bots fill remaining slots up to the target headcount.

## 9. Technical architecture

- **Authoritative Elixir server.** Required: clients must NOT know the human/bot mapping,
  and the server must be cheat-proof.
- **Client-side prediction + interpolation** so movement feels instant despite server
  authority (directly addresses the "server in charge = laggy UX" concern).
- **Phoenix Channels** (websockets) for transport.
- **One GenServer per room**, supervised; a **single ~20Hz tick** that simulates the
  world AND broadcasts state (split sim/broadcast later only if needed).
- **State sync:** full **quantized snapshots** at ~20Hz (≈ tens of KB/s per client at
  100 entities — trivial for the BEAM). Clients **interpolate** other entities and
  **predict** their own input, reconciling against snapshots. (Delta compression is a
  later optimization, not needed for MVP.)
- **Client renderer:** **Pixi.js / WebGL** canvas.
- **Persistence:** **Ecto + Postgres** for accounts + stats/leaderboards.
- **Auth / onboarding:** **guest play allowed** (name only, jump straight in); optional
  account to persist stats. Stats are only tracked for logged-in players.

## 10. Explicitly rejected (so we don't reintroduce them)

These were considered and **cut** — do not add back without a deliberate decision:

- ❌ Auto-scrolling camera / death-wall / "fall off the left edge = die."
- ❌ 2D movement, up/down repositioning, leftward/backward movement.
- ❌ Muzzle flash / gun sprite / "gun-out" exposure animation on firing.
- ❌ "No visible aim" / private crosshairs (crosshairs ARE public).
- ❌ Stamina-limited running, speed tiers, projectile (non-hitscan) bullets.
- ❌ Round timer (the racing bots are the clock).
- ❌ Phoenix LiveView for the game loop.
- ❌ Kill reveal — a kill announcing human-vs-bot. Firing now reveals nothing (§5).
- ❌ Per-tick bot speed variation / bots faster than a human walk (bots move at the walk
  speed in steady phases; §4).

---

## Open / deferred (post-MVP)

- `botNoise` dial (fake flinches, odd pauses) to add false positives.
- A few "eager" bots that lunge for the finish to give a winning dash some cover.
- Delta-compressed snapshots if bandwidth ever becomes a concern.
- Decoupling the sim tick from the broadcast tick for scale.
