# Dead Giveaway — Architecture

How the game is *built*. This is the engineering companion to [`DESIGN.md`](../DESIGN.md),
which describes what the game *is* and why each mechanic exists. Where they overlap, DESIGN
is the source of truth for intent; this doc is the source of truth for the moving parts.

> **TL;DR** — An authoritative Elixir/Phoenix server runs one supervised GenServer per
> room. Each room owns a *pure* simulation that ticks at 20 Hz and broadcasts full-state
> snapshots over a Phoenix Channel. A Pixi.js/WebGL client renders those snapshots by
> interpolation. The snapshot **never** contains the human/bot mapping — secrecy is a
> server-enforced invariant, not a client courtesy.

---

## 1. Technology stack

| Layer | Choice | Notes |
|---|---|---|
| Language / runtime | **Elixir** on the **BEAM** (OTP) | Cheap processes + supervision = one isolated GenServer per room. |
| Web framework | **Phoenix 1.8** | Channels for the game socket; plain controllers for pages. **No LiveView in the game loop** (DESIGN §10). |
| HTTP server | **Bandit** | Phoenix's default adapter. |
| Transport | **Phoenix Channels** (WebSockets) | One channel per connected player per room. |
| Persistence | **Ecto + Postgres** | Registered players and their cumulative wins only (DESIGN §8). |
| Client renderer | **Pixi.js / WebGL** | Sprite atlas, letterboxed 1280×720 design resolution. |
| Client bundling | **esbuild** (JS) + **Tailwind v4** (CSS) | Single `app.js` / `app.css` bundle; no external `src`/`href`. |
| Audio | **WebAudio** | Theme-aware lobby loop + 4-stage escalating in-round score; a Ports-&-Adapters "music director". |
| Deploy | **Fly.io** + Docker | Push-to-`main` auto-deploys via GitHub Actions. |

Pure-vs-effectful is the organizing principle on both sides of the wire:

- **Server:** `World` (the sim) and `Session` (lobby + scoreboard) are **pure** modules —
  data in, data out, no processes — wrapped by the stateful `Room` GenServer that owns the
  timers, PubSub, and the DB side effect. The purity is what makes the sim deterministic
  and unit-testable.
- **Client:** coordinate math (`coords.mjs`) and audio policy (`music-director.mjs`) are
  pure and unit-tested; `game.mjs` is the Pixi + socket + DOM glue around them.

---

## 2. The big picture

```
 ┌─────────────────────────────── BROWSER ───────────────────────────────┐
 │  app.js  → router.mjs (client-side nav)                                │
 │            └─ game.mjs  ── Pixi scene ── coords.mjs (pure)             │
 │               │                                                        │
 │               ├─ audio-shell.mjs (singleton) ── music-director.mjs    │
 │               │     lobby loop + escalating game score (WebAudio)      │
 │               │                                                        │
 │               └──────── Phoenix Channel "room:CODE" ────────┐          │
 └─────────────────────────────────────────────────────────────┼─────────┘
                                                                │ WebSocket
 ┌──────────────────────────── ELIXIR / BEAM ───────────────────┼─────────┐
 │  DeadGiveaway.Application (supervision tree)                  │         │
 │    ├─ Phoenix.PubSub  ◄── broadcasts ──┐                      ▼         │
 │    ├─ RoomRegistry (Registry)          │      DeadGiveawayWeb.Endpoint  │
 │    ├─ RoomSupervisor (DynamicSupervisor)│            └─ RoomChannel ─────┤
 │    │     └─ Room (GenServer, 1 per code) ┘                  (1 per       │
 │    │          ├─ World   (pure sim)                          player)     │
 │    │          ├─ Session (pure lobby+score)                             │
 │    │          └─ 20 Hz tick → snapshot → PubSub.broadcast               │
 │    └─ Repo (Ecto/Postgres) ── Accounts (wins/leaderboard)               │
 └─────────────────────────────────────────────────────────────────────────┘
```

A room's snapshot stream is **one PubSub broadcast per tick** to the topic `room:CODE`;
every `RoomChannel` subscribed to that topic forwards it down its own socket (after
anonymizing crosshairs — see §6).

---

## 3. Server process model

### Supervision tree (`DeadGiveaway.Application`)

Started once at boot:

- **`Phoenix.PubSub`** — the broadcast bus rooms publish snapshots/events on.
- **`RoomRegistry`** (`Registry`, unique keys) — maps a room code → the room's pid.
- **`RoomSupervisor`** (`DynamicSupervisor`, `:one_for_one`) — starts/owns room processes
  on demand.
- **`Repo`** — the Ecto/Postgres connection pool.
- **`Endpoint`** — the Phoenix/Bandit web server.

### Rooms are started on demand (`DeadGiveaway.Rooms`)

`Rooms.find_or_start/2` is the idempotent door: it asks the `DynamicSupervisor` to start a
`Room` registered under a `:via` tuple in the `Registry`. Concurrent or repeated calls for
the same code resolve to the **same** process (`{:already_started, pid}` is treated as
success). `Rooms.whereis/1` is a pure lookup — it returns `nil` for a code with no live
room, which is how a **join-by-code** distinguishes "lobby exists" from "typo / already
ended."

### The Room GenServer (`DeadGiveaway.Room`)

One per active room code, `restart: :transient` (an empty room that times itself out exits
`:normal` and is *not* restarted; a genuine crash still is). The Room is the stateful shell
that:

- holds the lobby roster, host, and config knobs (in a `Session` struct);
- starts a round on **Go** (host-only) and tears it down on a finish;
- drives the **20 Hz tick**, stepping the `World` and broadcasting the snapshot;
- routes player input (`set_verb`, `aim`, `fire`) into the `World`;
- awards the win (and persists it for registered players) on a finish;
- shuts itself down ~60 s after the last player leaves, freeing the code.

Everything the Room knows that a client must *not* (who is human, who took over a bot, who
got knocked out) stays inside the process and is only ever revealed through the carefully
filtered snapshot or a privately-routed message.

### The pure simulation (`DeadGiveaway.World`)

`new/1 → tick/1 → snapshot/1` are plain functions. All randomness is driven by an injected
`:seed`, so a given seed always produces the same world — that determinism is what makes the
sim testable and replayable. Key responsibilities:

- **Spawn:** N human entities + M bots on fixed vertical rows; humans are assigned to
  *random* rows (identity is never positional), and cosmetic sprite variants are chosen
  client-side from a hash of the entity id — never correlated with human/bot (DESIGN §4).
- **Movement:** humans move by their player-set verb (`stop`/`walk`/`run`); bots run an
  independent move↔stop phase cycle with per-bot re-rolled durations, so the crowd is
  desynced and a *moving bot is indistinguishable from a walking human*. **No bot ever
  runs** — running is the one hard tell (DESIGN §3/§6). Round **pace** sets the bot
  move:stop ratio, never the speed.
- **Firing:** hitscan with a hit radius — kills the living body nearest the crosshair if
  within `@hit_radius`, else the shot whiffs (the bullet is spent either way). A kill
  returns a bare `:killed` — *nothing* about who/what was hit.
- **Death & takeover:** with >1 life, a dropped human silently inhabits the furthest-back
  free bot body (deterministic, no rng) instead of being knocked out (DESIGN §7).
- **Outcome:** first body across `finish_x` ends the round — `{:winner, player}` or `:wash`
  (a bot crossed first).
- **`snapshot/1`** is the *only* outward view and is defined to never leak the mapping (§6).

### The pure lobby/scoreboard (`DeadGiveaway.Session`)

A plain struct threaded through the Room's state: the monotonic-slot roster, the
name-assignment/uniquification policy, and the cumulative per-category scoreboard (today:
`:wins`, plus the shared "Bot" tally). Slots are monotonic and never reissued, so a `leave`
can never silently overwrite a still-present player. It has documented extension seams
(`bot_name`, `namer`, `clock`, multi-category scores) that all default to today's exact
behaviour.

---

## 4. The game loop

A round runs entirely inside one `Room` process. The tick is a self-rescheduling
`Process.send_after(self(), :tick, tick_ms)` — **`tick_ms: 50` in production = 20 Hz**. The
timer runs for the room's whole life and simply no-ops while no round is in progress, so
round resets never double-schedule it.

Each tick (`do_tick/1`), when a world is live:

1. `World.tick/1` advances every entity one step (humans by verb, bots by phase).
2. `World.snapshot/1` produces the public view; the Room attaches the **visible crosshairs**
   (each still-armed player's last-aimed point, keyed by name).
3. The snapshot is broadcast to `room:CODE` via PubSub.
4. If any body has crossed the finish line, the Room awards the outcome, broadcasts
   `round_over` with the scoreboard, and resets to the lobby (bumping the seed so the next
   round differs).

The whole world is re-sent every tick as a **full snapshot** — at ~100 entities this is
tens of KB/s per client, trivial for the BEAM, so there is no delta compression (deferred
until bandwidth ever matters; DESIGN §9). Snapshots currently ship **raw floats**;
quantizing them (DESIGN §9's intent) is a tracked, low-priority optimization, not yet done.

---

## 5. Server / client authority model

**The server is fully authoritative.** Clients are dumb terminals that send *intent* and
render *snapshots*; they never simulate gameplay.

What the client sends (intent):

- `input {verb}` — stop/walk/run.
- `aim {x, y}` — current crosshair point, throttled to ~snapshot rate, fire-and-forget.
- `fire {x, y}` — spend a bullet at a point; the reply says only `fired: true/false`.
- lobby messages — `go`, `set_config`, `leave`.

What the client does locally with **no** server round-trip:

- Draws **its own crosshair** directly at the mouse position (screen space).
- **Interpolates** every body and every peer crosshair toward its latest snapshot target
  (a 0.25 lerp per render frame), so 20 Hz snapshots render as smooth 60 fps motion.

### Why there is no client-side prediction of *your own* body

This is the subtle, defining consequence of hidden identity. The classic
authoritative-server pattern predicts the local player's movement to hide latency. **Dead
Giveaway can't** — and deliberately doesn't — because the client *does not know which
body is its own*. The player presses a key, the server applies the verb to their (secret)
entity, and the result arrives in the next snapshot like everyone else's. The only thing
rendered with zero latency is the **reticle**, which is decoupled from any body and is the
one element the client genuinely owns. So the perceived latency of "did that key do
anything?" is itself part of the game — finding yourself by moving and watching who responds
is the core opening move (DESIGN §2).

(DESIGN §9 lists "client-side prediction" as an aspiration; the shipped client interpolates
everything and predicts nothing, which is the correct read of the hidden-identity
constraint. The reticle is the prediction-free immediacy that makes it feel responsive.)

---

## 6. The hidden-identity invariant (the part that must not leak)

Secrecy is enforced at the server boundary, in layers. Every one of these is a deliberate
guard, cross-referenced to DESIGN §5/§7/§9:

1. **The snapshot carries no identity.** `World.snapshot/1` emits only
   `{id, row, x, verb, alive}` per entity plus `finish_x`. The `human?`/`player` fields
   exist *only* inside the world struct and are never serialized.

2. **Crosshairs are anonymized in the channel.** The Room keys crosshairs by player name
   (it's the trusted authority). `RoomChannel.anonymize_crosshairs/2` strips the
   recipient's own reticle (their client draws it live), drops all names, and emits a bare,
   name-sorted list of points. A reticle therefore never reveals whose it is or which body
   it sits on — only *where* someone is aiming (which is legitimate intel).

3. **A kill reveals nothing.** `fire` returns a bare `:killed`/`:spent`; the Room broadcasts
   only an anonymous `:shot` (no shooter, position, or outcome). The dropped body simply
   ghosts in the next snapshot. You never learn if you hit a human or a bot.

4. **Knock-out and lives are private, point-to-point.** When a body drops, the Room diffs
   liveness *before vs after* the shot and broadcasts `{:player_out, name}` /
   `{:chances, name, n}`. Every channel receives the broadcast, but **only the named owner's
   channel forwards it to its browser**. So the owner learns "you're out" / "you have N
   lives left" while peers see only an ordinary body that happens to start moving
   differently — a bot takeover is invisible to everyone but its owner.

5. **Host privilege is server-assigned.** The first joiner is the host; the flag is tracked
   server-side and echoed to clients, never read from the URL or a client `host` payload, so
   a crafted link can't seize a lobby or start a round.

6. **Player input is the only free text, and it's filtered once.** Names are trimmed,
   length-capped, and profanity-redacted at a single server chokepoint
   (`RoomChannel.normalize_name/1`).

The recurring pattern: *the Room knows everything; the wire knows the minimum.* Anything
identity-bearing either never leaves the struct, is stripped at the channel, or is routed to
exactly one recipient.

---

## 7. Network protocol

One channel, topic `room:CODE`. Join payload: `{host: bool, name: string}` (host is
create-intent only, not a grant).

**Client → server (`handle_in`):**

| Event | Payload | Effect |
|---|---|---|
| `input` | `{verb}` | Set the player's movement verb. |
| `aim` | `{x, y}` | Update crosshair point (no reply). |
| `fire` | `{x, y}` | Spend a bullet; reply `{fired: bool}`. |
| `go` | — | Start the round (host-only). |
| `set_config` | `{max_ammo \| max_chances \| theme \| pace}` | Lobby knob (host-only). |
| `leave` | — | Guest frees their seat; host closes the whole lobby. |

**Server → client (`push`):**

| Event | Payload | Meaning |
|---|---|---|
| `lobby` | `{players, host, max_ammo, max_chances, theme, pace}` | Roster + config (the lobby view). |
| `round_start` | `{}` | A round just began — clear the lobby, re-arm. |
| `snapshot` | `{entities[], finish_x, crosshairs[]}` | 20 Hz world state (crosshairs anonymized). |
| `shot` | `{}` | Someone fired (anonymous) — play the SFX. |
| `out` | `{}` | **Private:** your body dropped, you're out. |
| `chances` | `{chances}` | **Private:** your remaining lives (HUD). |
| `round_over` | `{winner, scores}` | Round ended; standings. |
| `closed` | `{}` | The host closed the lobby — go home. |

---

## 8. Lifecycle walk-throughs

**Create / join a room.** `/play/new` mints a 4-char code (alphabet excludes confusable
glyphs) and stows *create-intent* in the session cookie, then redirects to `/play/CODE`.
`GameController.show` renders the canvas page. `game.mjs` opens the socket and joins
`room:CODE` with `{host: wantsCreate, name}`. `RoomChannel.join` resolves the room
(`find_or_start` for a creator; `whereis`-or-`not_found` for a join-by-code), subscribes to
PubSub *before* joining so it receives its own join's lobby roster, and seats the player via
`Room.join`.

**A round.** The host clicks **Go** → `Room.go` builds a fresh `World` from the current
roster + config, broadcasts `round_start`, and the already-running tick begins emitting
snapshots. Clients hide the lobby card, reveal the ammo/lives HUD, and start rendering. The
tick runs until a body crosses `finish_x`; the Room awards the win (persisting it if the
winner is a registered player), broadcasts `round_over` + scoreboard, and drops back to the
lobby. Another **Go** ("Play again") starts the next round.

**A shot.** Client `fire {x,y}` → `Room.fire` snapshots liveness/lives *before*, calls
`World.fire`, then: broadcasts anonymous `:shot` if a bullet was spent; diffs liveness to
privately notify a newly knocked-out owner (`:player_out`); diffs lives to privately refresh
a taken-over owner's HUD (`:chances`). The reply to the shooter is only `{fired: bool}`. The
client decrements ammo off the *server's* reply (never optimistically), so the HUD can't
desync from real ammo.

**Death & takeover.** With one life, a dropped body = out (spectate). With more, `World`
silently moves the player into the furthest-back free bot body and spends a life — the
public snapshot is unchanged, only the owner's private `:chances` updates.

---

## 9. Client architecture

`assets/js/` is ES modules bundled by esbuild into one `app.js`.

- **`app.js`** — the per-page `mount()`. Re-runnable after each client-side nav: wires flash
  banners and the always-present audio gear, then boots the game (if `#game` is present) or
  the home splash.
- **`router.mjs`** — minimal client-side navigation for the home↔play hop, purely so the
  **persistent audio shell survives the move** instead of being destroyed by a full reload
  (#20). It fetches the destination, swaps `<body>`, runs the outgoing page's teardown, and
  updates history. Pure progressive enhancement — with no JS it degrades to ordinary
  full-page navigation.
- **`game.mjs`** — the Pixi scene + socket + input glue. Builds the world container
  (arena → floor → finish → entities), letterbox-scales a fixed **1280×720 design
  resolution** to the window, manages the sprite pool, interpolates bodies and peer
  reticles, handles keyboard (hold = walk, Shift = run) and mouse (move = aim, click =
  fire), and runs the lobby/HUD DOM. Renders at `devicePixelRatio` for crisp HiDPI output.
- **`coords.mjs`** — pure world↔screen transforms (unit-tested), independent of Pixi.
- **Audio** (`audio-shell.mjs`, `music-director.mjs`, `music.mjs`, `volume.mjs`) — a
  module-singleton "shell" owning two loops (menu + 4-stage escalating in-round score) and
  the firing SFX. The **music director** is pure Ports-&-Adapters policy ("which loop for
  which view, when to (re)play, autoplay-unlock") driven through one injected `AudioPort`,
  so it's testable with an in-memory recorder — no DOM, no AudioContext. The shell is a
  singleton specifically so the loop keeps playing across the client-side home↔play hop.

---

## 10. Themes

A room wears a cosmetic **theme** (host-set lobby knob, broadcast so everyone swaps
together). `DeadGiveaway.Themes` is the server-side catalogue (keys + display names only) —
it validates a host's pick and feeds the lobby picker. Each theme's actual assets live in a
**self-contained folder** under `priv/static/themes/<key>/` with a `theme.json` manifest
(atlas, backdrops, bullet icon, reticle colour, menu loop, game stages). The client's
`loadTheme()` reads the manifest and swaps every texture/loop at runtime; it only runs
between rounds (no entities are mid-flight). Adding a theme = drop a folder + add one
`@catalog` entry. **Cosmetic variants are never correlated with the human/bot mapping** —
see `priv/static/themes/README.md`.

---

## 11. Persistence

`Ecto + Postgres`, deliberately minimal. `DeadGiveaway.Accounts` owns registered players and
their cumulative **wins only** (DESIGN §8) — `record_win/1` is an atomic
`update_all [inc: [wins: 1]]` that returns `:ignored` for a guest (an unregistered name), so
guests are never tracked and the sim has no hard DB dependency (the stats sink is an
injected module, off by default in tests). The `/leaderboard` page ranks players by wins.
The simulation itself is entirely in-memory — only the win tally touches the database.

---

## 12. Deployment

- **Fly.io**, app `dead-giveaway-game`, region `iad`, single shared-cpu-1x / 512 MB machine
  with `auto_stop_machines` (scales to zero when idle).
- **Docker** multi-stage build; `config/runtime.exs` reads `DATABASE_URL`, `SECRET_KEY_BASE`,
  `PHX_HOST`, `ECTO_IPV6`, etc. at boot. The release runs migrations via
  `/app/bin/migrate` as Fly's `release_command`.
- **CI/CD:** push to `main` triggers `.github/workflows/fly-deploy.yml`, which auto-deploys.
  Live at **https://dead-giveaway-game.fly.dev**.

> Because `main` auto-deploys, **run `mix test` before merging** and do all work on a branch
> via pull request.

---

## 13. Testing strategy

- **Pure cores are unit-tested directly.** `World` (movement, firing, takeover, outcomes,
  determinism via fixed seeds) and `Session` (roster, naming, scoring) need no processes.
- **`Room` is tested as a GenServer** with a tiny tick and no bots for determinism, often
  injecting a stub world module (`world_mod`) to assert the shell's orchestration in
  isolation.
- **`RoomChannel`** is tested with Phoenix's `ChannelCase` — join, input routing, and the
  crosshair-anonymization / privacy guarantees.
- **Controllers** cover the page/leaderboard/room-creation routes.
- **Client purity is unit-tested in JS** (`*.test.mjs`): `coords`, `music`, `volume`, and
  the `music-director` policy against an in-memory port.

Run it all with `mix test` (Elixir) and `npm test --prefix assets` (JS). `mix precommit`
runs `compile --warnings-as-errors`, `format`, `credo --strict`, and the test suite.

---

## 14. Where to extend

- **Bandwidth at scale:** delta-compressed snapshots; split the sim tick from the broadcast
  tick (DESIGN §9 deferred).
- **False positives:** a `botNoise` dial (fake flinches/pauses) and a few "eager" bots
  (DESIGN open items).
- **Scoreboards beyond wins:** `Session` already carries a per-category `scores` map and a
  `credit/4` primitive — e.g. a "most accurate shooter" `:kills` board — without touching
  outcome routing.
- **More themes:** drop a pack folder + one `Themes.@catalog` entry.
```
