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
- **Controls:** hold **Space** to walk, hold **Shift** to run, release to stop. Mouse
  aims; click fires.
- **Run is faster than any bot ever moves. Bots cannot run.** So *running is always an
  unmistakable human tell* — a pure last resort.
- Pace / being at the front of the pack is a *soft, fuzzy* tell, not a hard one.

## 4. The crowd (bots)

- Headcount scales with players (~6 bots per human, cap ~100). MVP target ~30.
- Characters are scattered at fixed vertical rows and draw from a **shared pool of ~12
  cosmetic sprite variants** (each with idle / walk / run animations). Each character's
  variant is derived **client-side from a deterministic hash of its entity id** — so every
  client shows a given character the same way, the look is **NEVER correlated with who is
  human**, and no variant data need ride the snapshot. It is pure decoration so the crowd
  reads as a crowd, not a row of clones. Because identity is re-rolled each round (humans
  take random bodies), the same variant can be a human in one round and a bot in the next;
  cosmetics leak no identity. Per-theme art lives in `priv/static/themes/<theme>/`.
- Each bot independently **moves or stops in alternating phases**, the duration of each
  phase re-rolled per cycle on its own timing — so the crowd is desynced (no "waves") with
  no mid-phase jitter. A moving bot moves at **exactly the human walk speed**, so pace
  never distinguishes a walking human from a moving bot; only *running* (which no bot can
  do) is a hard tell. Longer stop phases keep overall progress in check.
- The **round tempo** (`slow | medium | fast`) is a host-set lobby knob that tunes the
  bots' move:stop *ratio* — how much of the time the crowd spends moving, and so how fast
  the race runs overall — **not** how fast a moving body goes (that stays pinned to the
  walk speed, so tempo can never become a tell).
- Bots **race toward the finish** (they can and do cross it).
- **No bot "noise" for v1** (no fake flinches/pauses/etc.). A `botNoise` dial may be
  added later to introduce false positives.

## 5. Crosshairs & the bullet

- **Everyone sees every crosshair.** Each player has a visible floating reticle.
- You find **your own** crosshair at the start by **moving the mouse**.
- A crosshair is **decoupled from any character body** — seeing a reticle does NOT tell
  you which character its owner is. But *where* a reticle hovers is intel (a reticle
  parked on someone = that someone is suspected).
- **One bullet per player per round** by default — the lobby host can raise the count
  (up to a handful) before a round. Hitscan **with a hit radius**: a shot kills the living
  character nearest the crosshair, but **only if one is within a small radius** — otherwise
  the bullet cracks out over empty ground and hits nothing (a miss). A hit and a miss
  **both spend the shot**; only being out of ammo (or out of the round) costs you nothing.
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
- **Lives ("chances") per round** are a lobby knob, host-set like the bullet count and
  defaulting to **1**. With one life, getting shot (or shooting yourself) = **out for the
  round**, spectate; the round continues until someone crosses.
- With **more than one life**, a player whose body drops **takes over a free bot body**
  instead of being knocked out, spending one life — they seamlessly keep playing in a new
  character (the living bot furthest back, so a second life re-enters you at the back of
  the pack). They're only out once they're **out of lives, or no free bot remains**.
  - The takeover is **private to the owner** (DESIGN §5): the public snapshot never says
    who controls a body and the owner keeps their same anonymous crosshair, so peers can't
    tell "character X is now the human who was character Y." The owner's client is told
    directly (their lives HUD updates); everyone else sees only an ordinary body that
    happens to start moving differently.

## 8. Session / match structure

- **Endless rounds** with a between-rounds **lobby**: a finish drops everyone out and shows
  the standings, and the **host** starts the next round from there ("Play again"). Players
  join/leave freely.
- **Cumulative scoreboard** across the session. **Wins only score** (kills are tactics,
  not points).
- A round can start with **as few as one player** (a lone player races the bots); the
  **host** alone starts it. Mid-round joiners **spectate until the next round**.
- Bots fill remaining slots up to the target headcount.
- **Lobbies are addressed by a short shareable code.** Creating one mints the code and makes
  that creator the **host**; others join by typing the code. Host privilege is assigned
  **server-side** (never from the URL), hands off to the earliest remaining player if the
  host leaves, and is what gates **starting a round** and **changing the lobby knobs**
  (bullets, lives, tempo, theme). The host can **close** the lobby for everyone; an empty
  lobby **expires** on its own shortly after the last player leaves, freeing its code.

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
- **Cosmetic themes:** a room wears a host-set **theme** (art + audio), chosen in the lobby
  and broadcast so every client swaps together; it can be hot-swapped between rounds. Each
  theme is a self-contained pack under `priv/static/themes/<key>/` with a `theme.json`
  manifest, and is **purely cosmetic** — never correlated with identity.
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
