# Dead Giveaway

**A browser multiplayer hidden-identity game.** Hide among a crowd of identical AI
characters racing across a room, blend in, and be first across the finish line — without
getting picked off by the other humans hiding in the same crowd.

🎮 **Play it live:** [dead-giveaway-game.fly.dev](https://dead-giveaway-game.fly.dev)

> Inspired by the *Death Race* mode from *Hidden in Plain Sight*. We borrow the gameplay
> layout only — not the art.

---

## The twist

At spawn **you don't know which character is you.** Your inputs drive your real body from
the first frame, but you have to *deduce* which one it is by moving and watching who
responds — and that probing is the most human-looking thing you can do, so the opening
seconds are when you're most exposed.

- **Move right only** — stop, walk, or **run**. Running is faster than any bot can ever
  move, so it's an unmistakable human tell. A pure last resort.
- **Bots are indistinguishable from a walking human** — same speed, same sprites (cosmetics
  are random and never tied to who's human).
- **One bullet** (host can raise it). Hitscan kills the body nearest your crosshair. A kill
  reveals *nothing* — not who fired, not whether you hit a human or a bot. Every shot is a
  gamble.
- **First across the line wins** — player or bot. A bot crossing first is the natural
  shot-clock.

The full game design lives in **[`DESIGN.md`](DESIGN.md)**.

---

## Quick start

**Prerequisites:** Elixir (~> 1.15) + Erlang/OTP, Node.js (for esbuild + the Pixi.js
client), and PostgreSQL running locally.

```bash
mix setup            # install deps, create + migrate the DB, build assets
mix phx.server       # start the server (or: iex -S mix phx.server)
```

Then open **http://localhost:4000**. Click *Create* to mint a lobby code, share it, and
(as host) hit **Go** to start — solo against the bots, or once friends have joined by code.

### Tests

```bash
mix test                      # Elixir: sim, lobby, room, channel, controllers
npm test --prefix assets      # JS: coords + audio policy (pure modules)
mix precommit                 # compile (warnings-as-errors), format, credo, test
```

---

## Tech stack

- **Server:** Elixir / Phoenix 1.8 on the BEAM — one supervised GenServer per room, a pure
  20 Hz simulation, Phoenix Channels (WebSockets) for transport. **No LiveView in the game
  loop.**
- **Client:** Pixi.js / WebGL canvas, bundled with esbuild; Tailwind v4 for the surrounding
  pages; a WebAudio music/SFX shell.
- **Persistence:** Ecto + Postgres — registered players' cumulative wins only (guests play
  without an account).
- **Deploy:** Fly.io + Docker; push to `main` auto-deploys via GitHub Actions.

**The server is fully authoritative and the human/bot mapping never crosses the wire** — the
secrecy that makes the game work is a server-enforced invariant, not a client courtesy. How
all of that fits together is documented in **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)**.

---

## Project layout

```
lib/dead_giveaway/            # core domain
  world.ex                    # the pure, authoritative simulation (tick/snapshot)
  session.ex                  # pure lobby roster + scoreboard
  room.ex                     # the GenServer shell: tick, broadcast, lifecycle
  rooms.ex                    # registry + dynamic supervisor for rooms
  themes.ex / accounts.ex     # theme catalogue / registered-player stats
lib/dead_giveaway_web/
  channels/room_channel.ex    # the game socket (anonymizes everything identity-bearing)
  controllers/                # home, game page, leaderboard, room creation
assets/js/                    # Pixi client, coords, audio shell + director, router
priv/static/themes/<key>/     # self-contained theme packs (art + audio + manifest)
docs/ARCHITECTURE.md          # how it's all built
DESIGN.md                     # what the game is and why
```

---

## Documentation

- **[`DESIGN.md`](DESIGN.md)** — the game design spec: mechanics, the hidden-identity
  rules, what's deliberately rejected.
- **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** — the engineering doc: process model,
  the tick loop, server/client authority, the secrecy invariant, the network protocol,
  client architecture, themes, persistence, and deployment.
- **[`priv/static/themes/README.md`](priv/static/themes/README.md)** — how theme packs work
  and how to add one.
- **[`AGENTS.md`](AGENTS.md)** — conventions for working in this codebase.
