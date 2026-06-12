defmodule DeadGiveaway.Room do
  @moduledoc """
  A single Dead Giveaway room: one GenServer owning the authoritative `World` for
  the players inside it. Supervised, one per room (DESIGN §9).

  The Room is the stateful shell around the pure `DeadGiveaway.World`: it tracks who
  is in the lobby, starts a round when someone hits **Go**, drives the sim tick,
  broadcasts snapshots, routes player input into the world, and on a finish awards
  the win and drops everyone back to the lobby.

  Flow: players join the lobby (each gets a "Player N" name), then any player
  hits Go (`go/1`) to start a round with everyone currently in the lobby — a lone
  player may play against the bots. A finish tears the round down and returns to
  the lobby, where another Go starts the next round (§8).
  """

  # `:transient` so an empty room that stops itself (`:expire`, a `:normal` exit)
  # is NOT restarted by its supervisor; a genuine crash still is.
  use GenServer, restart: :transient

  alias DeadGiveaway.{Presence, Session, Themes, World}

  # A round can start with as few as this many players (the rest are bots).
  @min_players 1

  # Bullets-per-round is host-configurable in the lobby; default 1 (DESIGN §5),
  # clamped to this range so a stray client value can't hand out absurd ammo.
  @min_ammo 1
  @max_ammo 6

  # Lives-per-round (chances) is the other host knob; default 1 = one life, the
  # original "shot = out" behaviour. Above 1, a dropped player takes over a free bot
  # instead of being knocked out (DESIGN §7). Clamped so a stray value can't grant
  # near-endless lives.
  @min_chances 1
  @max_chances 5

  # The bots race as a single shared opponent on the scoreboard: any bot crossing
  # first credits this one tally (DESIGN §7 — what the sim reports as a "wash").
  @bot_name "Bot"

  # --- Client API ---

  def start_link(opts) do
    # When started via `Rooms` the room registers under a `:via` name so it's
    # addressable by id; standalone (e.g. in unit tests) it stays unnamed.
    gen_opts = if name = opts[:name], do: [name: name], else: []
    GenServer.start_link(__MODULE__, opts, gen_opts)
  end

  @doc """
  Join the room's lobby. Returns `{:ok, slot, name, host?}`: the assigned slot, the
  player's name, and whether this player is the room's host. Pass `nil` to be
  auto-named `"Player N"` (the default) — the lowest free number, so a slot freed by
  a leaver is reused rather than the count climbing forever; an explicit name is kept
  but disambiguated if already taken, since the name is also the player's identity and
  two players must never collapse onto one body. The first player to join is the host
  (DESIGN §9): the privilege is assigned here, server-side, never claimed by the
  client, so a hand-crafted URL can't seize a lobby out from under its owner.
  """
  def join(room, player \\ nil), do: GenServer.call(room, {:join, player})

  @doc "Leave the room, freeing the player's slot so they stop counting toward rounds."
  def leave(room, player), do: GenServer.call(room, {:leave, player})

  @doc """
  Rename a seated player while the room sits in the lobby (#63). The new name gets
  the same collision disambiguation a join does, and the refreshed roster is
  broadcast to everyone. Returns `{:ok, assigned_name}`, or `:error` when a round is
  live (names are identity mid-round — input/fire/aim are all keyed by them) or the
  player isn't seated.
  """
  def rename(room, player, new_name), do: GenServer.call(room, {:rename, player, new_name})

  @doc """
  Tear the room down entirely (the host backing out of the lobby). Tells every
  connected client the lobby has `:closed` so they can drop back home, then stops
  the room — freeing its code immediately rather than waiting for the empty timer.
  """
  def close(room), do: GenServer.call(room, :close)

  @doc "Start a round from the lobby with everyone currently joined (the Go button)."
  def go(room), do: GenServer.call(room, :go)

  @doc """
  Set how many bullets each player gets next round (DESIGN §5), clamped to a sane
  range. Takes effect from the next Go; ignored mid-round. A lobby-config knob, so
  the new value is broadcast to everyone's lobby view.
  """
  def set_max_ammo(room, n), do: GenServer.call(room, {:set_max_ammo, n})

  @doc """
  Set how many lives each player gets next round (DESIGN §7), clamped to a sane range.
  Like the bullet count it takes effect from the next Go, is ignored mid-round, and is
  broadcast to every lobby view.
  """
  def set_max_chances(room, n), do: GenServer.call(room, {:set_max_chances, n})

  @doc """
  Set the room's cosmetic theme (`DeadGiveaway.Themes`). Like the bullet count it's a
  host-set lobby knob: an unknown key keeps the current theme, and a change is broadcast
  to everyone's lobby view so all clients swap art/audio together. Ignored mid-round.
  """
  def set_theme(room, theme), do: GenServer.call(room, {:set_theme, theme})

  @doc """
  Set the round's pace `slow | medium | fast` (#17) — the bot move:stop ratio. Like the
  other lobby knobs it's host-set, takes effect from the next Go (ignored mid-round), and
  is broadcast to every lobby view. An unknown value keeps the current pace.
  """
  def set_pace(room, pace), do: GenServer.call(room, {:set_pace, pace})

  @doc """
  Set the game mode `classic | red_light` (#53). Like the other round knobs it's
  host-set, takes effect from the next Go (ignored mid-round), and is broadcast to
  every lobby view. An unknown value keeps the current mode.
  """
  def set_mode(room, mode), do: GenServer.call(room, {:set_mode, mode})

  @doc """
  List or unlist the lobby in the public directory (issue #43). Public lobbies show up
  in the home page's "open lobbies" panel and are joinable in one click; private ones
  (the default) are code-only. Unlike the round knobs this isn't round config, so it
  takes effect immediately and is allowed mid-round — a public room stays listed (badged
  in-progress) while a race runs. Host-set, and broadcast to every lobby view.
  """
  def set_visibility(room, public), do: GenServer.call(room, {:set_visibility, public})

  @doc "Round status: `:waiting` until a round is running, then `:running`."
  def status(room), do: GenServer.call(room, :status)

  @doc "Set a player's movement verb (`:stop | :walk | :run`)."
  def set_verb(room, player, verb), do: GenServer.call(room, {:set_verb, player, verb})

  @doc """
  Record where a player's crosshair is hovering (world coords `{x, y}`). Everyone
  sees every crosshair, so this last-aimed point rides the snapshot stream out to
  the room (DESIGN §5). Fire-and-forget (a `cast`) since the mouse fires constantly
  and the reticle only needs to be roughly current, not acknowledged.
  """
  def aim(room, player, {_x, _y} = crosshair), do: GenServer.cast(room, {:aim, player, crosshair})

  @doc """
  Fire a player's bullet at crosshair `{x, y}`. Returns `:fired` once the shot
  is spent or `:no_shot` if the player has no bullet / no body. The shot's
  outcome (who or what it hit) is deliberately never revealed — firing tells
  no one anything (DESIGN §5).
  """
  def fire(room, player, crosshair), do: GenServer.call(room, {:fire, player, crosshair})

  @doc "Advance the sim by one tick and return `{:ok, snapshot}`. Used to drive a round."
  def tick(room), do: GenServer.call(room, :tick)

  @doc "Cumulative wins for a player this session (DESIGN §8 — wins only score)."
  def score(room, player), do: GenServer.call(room, {:score, player})

  @doc """
  PubSub topic the room broadcasts on (lobby, snapshots, and the private per-player
  signals). Deliberately NOT the channel transport's own topic (`"room:<id>"`): Phoenix
  auto-subscribes every channel process to its topic on the same PubSub, so sharing the
  string would deliver each broadcast to a channel twice — once via that built-in
  subscription and once via the channel's explicit subscribe in join (which must stay,
  it's what catches the joiner's own lobby broadcast before Phoenix's kicks in).
  """
  def topic(id), do: "room_events:#{id}"

  @doc "Display name of the shared bot opponent on the scoreboard."
  def bot_name, do: @bot_name

  # --- Server callbacks ---

  @impl true
  def init(opts) do
    tick_ms = Keyword.get(opts, :tick_ms)

    state = %{
      id: Keyword.fetch!(opts, :id),
      world_mod: Keyword.get(opts, :world, World),
      seed: Keyword.get(opts, :seed, :erlang.unique_integer([:positive])),
      # Fixed bot count when given (tests, tuning); nil scales the crowd to the
      # lobby at each round start (#37) — see scaled_bots/1.
      bots: Keyword.get(opts, :bots),
      finish_x: Keyword.get(opts, :finish_x),
      # Host-configurable bullets per player per round; defaults to one (DESIGN §5).
      max_ammo: clamp(Keyword.get(opts, :max_ammo, 1), @min_ammo, @max_ammo),
      # Host-configurable lives per player per round; defaults to one (DESIGN §7).
      max_chances: clamp(Keyword.get(opts, :max_chances, 1), @min_chances, @max_chances),
      # Host-configurable cosmetic theme (DESIGN §9); defaults to the catalogue head.
      theme: validate_theme(Keyword.get(opts, :theme, Themes.default()), Themes.default()),
      # Host-configurable round tempo (#17): the bot move:stop ratio. Defaults to :fast
      # (the original tempo); see DeadGiveaway.World for the presets.
      pace: validate_pace(Keyword.get(opts, :pace, World.default_pace()), World.default_pace()),
      # Host-configurable game mode (#53): classic, or red_light with the watcher.
      mode: validate_mode(Keyword.get(opts, :mode, World.default_mode()), World.default_mode()),
      # Whether this lobby is listed in the public directory (issue #43). Private by
      # default — code-only, discoverable to no one — until the host flips it public,
      # which tracks it in `DeadGiveaway.Presence` for the home page to browse.
      public: Keyword.get(opts, :public, false),
      # Whether we currently hold a `Presence` entry, so a sync knows to `track` the
      # first time vs `update` an existing entry vs `untrack` on going private.
      presence_tracked: false,
      # Optional persistence sink (a module with `record_win/1`, e.g.
      # DeadGiveaway.Accounts). Off by default so the sim has no DB dependency.
      stats_mod: Keyword.get(opts, :stats),
      tick_ms: tick_ms,
      # Shut an empty room down after this many ms idle so abandoned lobbies (and
      # their codes) don't pile up. `nil` (the default) disables expiry — handy
      # for unit tests that don't want a room vanishing under them.
      empty_after_ms: Keyword.get(opts, :empty_after_ms),
      expire_ref: nil,
      # The absolute (monotonic ms) deadline of the most recently scheduled tick —
      # what schedule_tick anchors the next delay to so timer lateness can't compound.
      next_tick_at: System.monotonic_time(:millisecond),
      # The pure lobby-and-scoreboard core: the monotonic-slot roster, name policy,
      # and the cumulative scoreboard (incl. the shared Bot tally). Room threads it
      # through state and delegates every roster read/write and scoring decision to it.
      session: Session.new(bot_name: @bot_name),
      # The host's name (DESIGN §9): the first player to join, reassigned to the
      # earliest remaining joiner if the host leaves, `nil` while the room is empty.
      # Only the host may reconfigure or close the lobby — and it's tracked here, not
      # taken from the client, so a crafted URL can't grant it.
      host: nil,
      world: nil,
      # Last-aimed crosshair point per player name, for the round in progress; the
      # snapshot carries the still-armed ones out. Cleared at every round boundary.
      crosshairs: %{}
    }

    # The tick timer (if any) runs for the room's lifetime; it idles while no
    # round is in progress, so round resets never double-schedule it.
    state = if tick_ms, do: schedule_tick(state), else: state
    # List the room straight away if it was created public (the host flow starts
    # private, so this only fires for an explicitly-public start, e.g. in tests).
    {:ok, sync_presence(state)}
  end

  @impl true
  def handle_call({:join, player}, _from, state) do
    {slot, name, session} = Session.join(state.session, player)
    # The first player in owns the room; everyone after joins as a guest.
    host = state.host || name

    # Joining only places you in the lobby — a round starts when someone hits Go.
    # A join means the room is no longer empty, so cancel any pending expiry.
    state =
      %{state | session: session, host: host}
      |> cancel_expiry()
      |> broadcast_lobby()

    {:reply, {:ok, slot, name, name == host}, state}
  end

  def handle_call({:leave, player}, _from, state) do
    # Session.leave retires the slot and drops the departed player's win tally (names
    # are reused, so a lingering score would otherwise be inherited by whoever next
    # takes that name; the shared Bot tally isn't a player, so it's left alone).
    session = Session.leave(state.session, player)
    # If the host left, hand the room to the earliest remaining joiner so the lobby
    # is never left without an owner. If that was the last player, start the
    # countdown to shut the room down.
    state =
      %{state | session: session}
      |> reassign_host(player)
      |> maybe_schedule_expiry()
      |> broadcast_lobby()

    {:reply, :ok, state}
  end

  def handle_call({:rename, player, new_name}, _from, %{world: nil} = state) do
    case Session.rename(state.session, player, new_name) do
      {:ok, name, session} ->
        # The host privilege is tracked by name — it must follow a renaming host.
        host = if state.host == player, do: name, else: state.host
        state = broadcast_lobby(%{state | session: session, host: host})
        {:reply, {:ok, name}, state}

      :error ->
        {:reply, :error, state}
    end
  end

  # Mid-round, names are pinned: every input/fire/aim and the world's slot map key on
  # them, so a rename waits for the lobby.
  def handle_call({:rename, _player, _new_name}, _from, state), do: {:reply, :error, state}

  def handle_call(:close, _from, state) do
    # Notify the room (the closing host included) before we go, so every client
    # navigates home rather than sitting on a lobby whose process is gone.
    broadcast(state.id, :closed)
    {:stop, :normal, :ok, state}
  end

  def handle_call(:go, _from, %{world: nil} = state) do
    state = if Session.count(state.session) >= @min_players, do: start_round(state), else: state
    {:reply, :ok, state}
  end

  # A round is already running — Go is a no-op (you're in it or spectating).
  def handle_call(:go, _from, state), do: {:reply, :ok, state}

  def handle_call(:status, _from, state) do
    {:reply, if(state.world, do: :running, else: :waiting), state}
  end

  # Ammo only reconfigures between rounds — a live round keeps the count it started
  # with, so a mid-round change can't hand a player extra bullets.
  def handle_call({:set_max_ammo, n}, _from, %{world: nil} = state) do
    state = broadcast_lobby(%{state | max_ammo: clamp(n, @min_ammo, @max_ammo)})
    {:reply, :ok, state}
  end

  def handle_call({:set_max_ammo, _n}, _from, state), do: {:reply, :ok, state}

  # Lives reconfigure only between rounds, same as ammo — a live round keeps the count
  # it started with.
  def handle_call({:set_max_chances, n}, _from, %{world: nil} = state) do
    state = broadcast_lobby(%{state | max_chances: clamp(n, @min_chances, @max_chances)})
    {:reply, :ok, state}
  end

  def handle_call({:set_max_chances, _n}, _from, state), do: {:reply, :ok, state}

  # Theme is cosmetic and reloaded client-side, so it only changes between rounds —
  # a live round keeps the look it started with rather than swapping mid-race.
  def handle_call({:set_theme, theme}, _from, %{world: nil} = state) do
    state = broadcast_lobby(%{state | theme: validate_theme(theme, state.theme)})
    {:reply, :ok, state}
  end

  def handle_call({:set_theme, _theme}, _from, state), do: {:reply, :ok, state}

  # Pace changes the next round's tempo, so like the other knobs it only applies between
  # rounds — a live race keeps the pace it started with.
  def handle_call({:set_pace, pace}, _from, %{world: nil} = state) do
    state = broadcast_lobby(%{state | pace: validate_pace(pace, state.pace)})
    {:reply, :ok, state}
  end

  def handle_call({:set_pace, _pace}, _from, state), do: {:reply, :ok, state}

  # Mode arms the next round (it's what the world is built with), so like the other
  # knobs it only applies between rounds — a live race keeps the mode it started with.
  def handle_call({:set_mode, mode}, _from, %{world: nil} = state) do
    state = broadcast_lobby(%{state | mode: validate_mode(mode, state.mode)})
    {:reply, :ok, state}
  end

  def handle_call({:set_mode, _mode}, _from, state), do: {:reply, :ok, state}

  # Visibility isn't round config (it's not a knob that arms the next race), so unlike
  # ammo/theme/pace it's accepted any time — including mid-round, where a public room simply
  # stays listed with its in-progress badge. Only a boolean is honoured; anything else is
  # ignored. The directory is always re-synced, but the :lobby roster is only re-broadcast
  # when we're actually in the lobby (world == nil): mid-round everyone's in-game, so pushing
  # :lobby then would re-run their lobby handler underneath a running round.
  def handle_call({:set_visibility, public}, _from, state) when is_boolean(public) do
    state = %{state | public: public}
    state = if state.world == nil, do: broadcast_lobby(state), else: sync_presence(state)
    {:reply, :ok, state}
  end

  def handle_call({:set_visibility, _public}, _from, state), do: {:reply, :ok, state}

  def handle_call({:set_verb, player, verb}, _from, state) do
    {:reply, :ok, update_world(state, &state.world_mod.set_verb(&1, player, verb))}
  end

  def handle_call({:fire, _player, _crosshair}, _from, %{world: nil} = state) do
    {:reply, :no_shot, state}
  end

  def handle_call({:fire, player, crosshair}, _from, state) do
    # Snapshot who's still standing (and their lives) before the shot, so we can tell
    # afterwards whose body dropped and whose life-count changed, and privately notify
    # those owners (DESIGN §5).
    states_before = player_states(state)

    {world, event} = state.world_mod.fire(state.world, player, crosshair)
    state = %{state | world: world}
    # The world resolves *which body* dies (it ghosts in the next snapshot), but
    # we never surface whether it was human or bot — to the shooter or anyone
    # else. A shot is a pure gamble (DESIGN §5). Both a hit (:killed) and a miss
    # (:spent) consume the bullet; only :no_shot leaves it in hand (#12).
    spent? = event in [:killed, :spent]

    # A spent bullet cracks out a shot everyone in the room hears, but the
    # broadcast stays anonymous — no shooter, position, or outcome — so firing
    # still tells no one anything (DESIGN §5).
    if spent?, do: broadcast(state.id, :shot)

    # Tell any player who was just knocked out — privately, to that owner alone — so
    # their client can drop its reticle and stop firing (#11). This rides a named
    # message every channel receives but only the owner forwards to its browser, so a
    # body dropping still leaks nothing to peers (DESIGN §5). A player who took over a
    # bot body instead (§7) is still alive, so no signal fires for them.
    states_after = player_states(state)
    notify_knocked_out(state, states_before, states_after)
    # A taken-over player stays alive but spent a life — refresh their lives HUD (§7).
    notify_chances(state, states_before, states_after)
    # A takeover also moved them into a new body — privately re-point their self
    # body-id so their client predicts the right one (#41).
    notify_bodies(state, states_before, states_after)

    {:reply, if(spent?, do: :fired, else: :no_shot), state}
  end

  def handle_call(:tick, _from, state) do
    {state, snapshot} = do_tick(state)
    {:reply, {:ok, snapshot}, state}
  end

  def handle_call({:score, player}, _from, state) do
    {:reply, Session.score(state.session, player), state}
  end

  # Crosshair updates only mean something during a live round; drop any that arrive
  # in the lobby (e.g. a client still moving the mouse over the field after a finish).
  @impl true
  def handle_cast({:aim, _player, _crosshair}, %{world: nil} = state), do: {:noreply, state}

  def handle_cast({:aim, player, crosshair}, state) do
    {:noreply, put_in(state.crosshairs[player], crosshair)}
  end

  @impl true
  def handle_info(:tick, state) do
    {state, _snapshot} = do_tick(state)
    {:noreply, schedule_tick(state)}
  end

  # The empty-room countdown elapsed. Stop only if still empty — a player may
  # have rejoined and cancelled the timer just as it fired (the message can
  # already be in the mailbox), in which case we stand down.
  def handle_info(:expire, state) do
    if Session.empty?(state.session) do
      {:stop, :normal, state}
    else
      {:noreply, %{state | expire_ref: nil}}
    end
  end

  # --- Internals ---

  # Host hand-off on a leave: only matters if the leaver *was* the host. The room
  # then passes to the earliest remaining joiner (the lowest slot, first in the
  # slot-ordered roster) — or to nobody once the room is empty.
  defp reassign_host(%{host: host} = state, left) when host != left, do: state

  defp reassign_host(state, _left) do
    new_host =
      case Session.players(state.session) do
        [%Session.Player{name: name} | _] -> name
        [] -> nil
      end

    %{state | host: new_host}
  end

  # The crowd scales with the lobby (#37, DESIGN §4/§8): ~6 bots per human, but bots
  # only fill what's left of the target headcount once the humans are seated. The
  # target is the MVP's ~30 (the design's eventual ceiling is ~100).
  @bots_per_human 6
  @target_headcount 30

  defp scaled_bots(humans) do
    min(humans * @bots_per_human, @target_headcount - humans) |> max(0)
  end

  defp start_round(state) do
    humans = Session.names(state.session)

    opts =
      [
        seed: state.seed,
        humans: humans,
        bots: state.bots || scaled_bots(length(humans)),
        max_ammo: state.max_ammo,
        max_chances: state.max_chances,
        pace: state.pace,
        mode: state.mode
      ]
      |> put_unless_nil(:finish_x, state.finish_x)

    # Tell clients the round is live so they can clear the lobby and re-arm.
    broadcast(state.id, :round_start)
    # Fresh round → fresh reticles; last round's aim points don't carry over.
    state = %{state | world: state.world_mod.new(opts), crosshairs: %{}}
    # A live round flips the directory entry to in-progress (if this room is listed).
    state = sync_presence(state)
    # Privately seed each player's lives HUD with their starting count (DESIGN §7) and
    # their self body-id for client-side prediction (#41).
    states = player_states(state)
    notify_chances(state, %{}, states)
    notify_bodies(state, %{}, states)
    state
  end

  # Advance one tick: step the world, broadcast the snapshot, and on a finish
  # award the win and reset for the next round.
  defp do_tick(%{world: nil} = state), do: {state, nil}

  defp do_tick(state) do
    # Only a Red Light tick can kill (the watcher, #53), so only there do we pay for
    # the before/after diff that routes the private death signals. Classic skips it.
    states_before = if state.mode == :red_light, do: player_states(state), else: nil

    world = state.world_mod.tick(state.world)

    snapshot =
      state.world_mod.snapshot(world)
      |> quantize_entities()
      |> Map.put(:crosshairs, visible_crosshairs(state, world))

    broadcast(state.id, {:snapshot, snapshot})
    state = %{state | world: world}
    notify_watcher_kills(state, states_before)

    state = maybe_finish(state, world)
    {state, snapshot}
  end

  # The three ways a round ends, judged once the tick's dust settles. A crossing is
  # checked first so winning the race always beats a same-tick walkover. Beyond the
  # line (#55, #59) it's down to who's still alive: every human out → game over with
  # no winner (watching the bots amble on helps no one); exactly one human left of
  # several → they win on the spot rather than strolling to an unthreatened line.
  # The walkover needs the round to have begun with company — a solo round must
  # still be raced (though a solo death still ends it).
  defp maybe_finish(state, world) do
    alive = state.world_mod.alive_players(world)

    cond do
      state.world_mod.finished?(world) ->
        finish_round(state)

      alive == [] ->
        finish_round(state, :wipe)

      match?([_], alive) and length(state.world_mod.players(world)) > 1 ->
        finish_round(state, {:winner, hd(alive)})

      true ->
        state
    end
  end

  # A body dropped by the watcher rides the exact same private signals as one dropped
  # by a bullet — owner knocked out / lives spent / re-pointed at a new body (#53) —
  # and the room hears the same anonymous crack. One crack covers simultaneous kills
  # (a rare double death isn't worth a per-body replay).
  defp notify_watcher_kills(_state, nil), do: :ok

  defp notify_watcher_kills(state, states_before) do
    states_after = player_states(state)
    notify_knocked_out(state, states_before, states_after)
    notify_chances(state, states_before, states_after)
    notify_bodies(state, states_before, states_after)

    if Enum.any?(states_before, fn {name, before} -> body_dropped?(before, states_after[name]) end),
       do: broadcast(state.id, :shot)
  end

  # Whether this player's body dropped across the tick: knocked out (alive flipped),
  # or moved into a fresh body (a takeover — the old body is now a corpse).
  defp body_dropped?({true, _, _}, {false, _, _}), do: true
  defp body_dropped?({true, _, body}, {true, _, body2}), do: body != body2
  defp body_dropped?(_before, _after), do: false

  # Each joined player's `{alive?, lives-left, body-id}` for the live round, keyed by
  # name (empty in the lobby, so a fire that somehow lands there notifies no one). One
  # walk feeds the knock-out, lives-HUD and self-body diffs around a shot; all three stay
  # private — none of liveness, lives or ownership ever rides the public snapshot
  # (DESIGN §5).
  defp player_states(%{world: nil}), do: %{}

  defp player_states(state) do
    for name <- Session.names(state.session), into: %{} do
      {name,
       {state.world_mod.player_alive?(state.world, name),
        state.world_mod.chances_left(state.world, name),
        state.world_mod.body_of(state.world, name)}}
    end
  end

  # Privately tell each owner whose body dropped this shot that they're out for the
  # round. Compares post-shot liveness against `before`: a name that was alive and is
  # now down gets a personal `:player_out`. A taken-over player (still alive) doesn't
  # transition, so they're correctly left alone (DESIGN §5, §7).
  defp notify_knocked_out(state, before, after_states) do
    for {name, {true, _, _}} <- before, match?({false, _, _}, after_states[name]) do
      broadcast(state.id, {:player_out, name})
    end
  end

  # Privately push each player whose life-count changed (or all of them, when `before`
  # is empty at round start) their current lives, for the HUD (DESIGN §7). Routed per
  # owner by the channel, so a takeover stays invisible to peers (DESIGN §5).
  defp notify_chances(state, before, after_states) do
    for {name, {_, n, _}} <- after_states, chances_in(before, name) != n do
      broadcast(state.id, {:chances, name, n})
    end
  end

  # Privately tell each owner which body they drive — their entity id — at round start
  # and again whenever it changes (a bot takeover, §7), so their client can predict its
  # own motion (#41). Routed per owner by the channel like the other private signals:
  # peers never learn whose body is whose, and only the recipient's OWN id ever leaves
  # the server — the full human/bot mapping stays private (DESIGN §2, §9).
  defp notify_bodies(state, before, after_states) do
    for {name, {_, _, body}} <- after_states, body != nil, body_in(before, name) != body do
      broadcast(state.id, {:you_are, name, body})
    end
  end

  # A player's lives from a `player_states/1` map, or nil when absent (e.g. an empty
  # `before` at round start, where every count then reads as changed and gets seeded).
  defp chances_in(states, name) do
    case states do
      %{^name => {_, n, _}} -> n
      _ -> nil
    end
  end

  # A player's body id from a `player_states/1` map, same shape as `chances_in/2`.
  defp body_in(states, name) do
    case states do
      %{^name => {_, _, body}} -> body
      _ -> nil
    end
  end

  # The crosshairs to ship with this snapshot: each still-armed, still-alive player's
  # last-aimed point, keyed by name. The channel anonymises this before it reaches any
  # browser — drops the names and the recipient's own — so a reticle never reveals whose
  # it is or which body it sits on (DESIGN §5). A player out of lives loses their reticle
  # for everyone (#61) — a takeover repoints them at the new body the same tick, so this
  # only drops players who are fully out.
  defp visible_crosshairs(state, world) do
    for {name, {x, y}} <- state.crosshairs,
        state.world_mod.armed?(world, name),
        state.world_mod.player_alive?(world, name),
        into: %{},
        do: {name, %{x: round(x), y: round(y)}}
  end

  # Round positions to whole world units before the snapshot goes on the wire (#39,
  # DESIGN §9 "full quantized snapshots"). The internal world keeps full float precision;
  # only the broadcast payload is quantized, shrinking the JSON (long raw floats → short
  # ints) with no visible effect — the client's 0.25 interpolation lerp hides the integer
  # stepping. Crosshairs are quantized above for the same reason.
  defp quantize_entities(%{entities: entities} = snapshot) do
    %{snapshot | entities: Enum.map(entities, &%{&1 | x: round(&1.x)})}
  end

  defp finish_round(state), do: finish_round(state, state.world_mod.outcome(state.world))

  defp finish_round(state, outcome) do
    # Award first so the broadcast carries the up-to-date session scoreboard.
    state = award(state, outcome)
    broadcast(state.id, {:round_over, outcome, Session.scoreboard(state.session)})
    reset_round(state)
  end

  # The pure tally moves into Session; the persistence side effect (record a win for
  # registered players — guests are ignored by the sink) stays here in the shell. A
  # `:wash` or any non-winner outcome has no player behind it, so nothing is persisted.
  defp award(state, outcome) do
    case outcome do
      {:winner, player} -> if state.stats_mod, do: state.stats_mod.record_win(player)
      _ -> :ok
    end

    %{state | session: Session.award(state.session, outcome)}
  end

  # Drop back to the lobby: re-seed and tear down the world. The next round
  # won't start until a player hits Go (§8).
  defp reset_round(state) do
    state = %{state | seed: state.seed + 1, world: nil, crosshairs: %{}}
    # Back in the lobby: broadcast_lobby re-syncs the directory, clearing the
    # in-progress badge for a listed room.
    broadcast_lobby(state)
  end

  defp update_world(%{world: nil} = state, _fun), do: state
  defp update_world(state, fun), do: %{state | world: fun.(state.world)}

  # Schedule the next tick against an absolute deadline, not relative to "after this
  # tick's work": send_after fires late by the work time plus the OS timer quantum
  # (~15.6ms on Windows), and rescheduling relative-to-now compounds that lateness into
  # a permanently slower tick rate (measured ~24% slow on Windows — 62ms per nominal
  # 50ms tick). Clients assume exactly tick_ms per tick when predicting their own
  # motion (#41), so a slow room makes every prediction race ahead and snap back.
  # Anchoring each delay to the running deadline lets a late tick shorten the next
  # delay, pinning the *average* period to tick_ms. A room that falls more than a full
  # tick behind (a suspended VM, a long stall) re-bases to now rather than
  # burst-ticking through the backlog.
  defp schedule_tick(state) do
    now = System.monotonic_time(:millisecond)
    deadline = max(state.next_tick_at + state.tick_ms, now)
    Process.send_after(self(), :tick, deadline - now)
    %{state | next_tick_at: deadline}
  end

  # Arm the shutdown timer when the room empties (no-op if expiry is disabled or
  # the room still has players). Always clears any prior timer first so leaves
  # can't stack up multiple pending expiries.
  defp maybe_schedule_expiry(%{empty_after_ms: nil} = state), do: state

  defp maybe_schedule_expiry(state) do
    if Session.empty?(state.session) do
      state = cancel_expiry(state)
      %{state | expire_ref: Process.send_after(self(), :expire, state.empty_after_ms)}
    else
      state
    end
  end

  defp cancel_expiry(%{expire_ref: nil} = state), do: state

  defp cancel_expiry(%{expire_ref: ref} = state) do
    Process.cancel_timer(ref)
    %{state | expire_ref: nil}
  end

  defp broadcast(id, message) do
    Phoenix.PubSub.broadcast(DeadGiveaway.PubSub, topic(id), message)
  end

  # The lobby roster — who's currently waiting to play, and who hosts — plus the room
  # config the lobby UI reflects (the host-set bullet count, theme, and public/private
  # visibility). Carrying the host's name lets every client tell whether it's the host
  # (and keep up if that changes), so host privilege is read from the server, never from
  # the URL. Returns the state with its directory entry synced (see `sync_presence/1`), so
  # callers thread it back — every lobby change keeps the public listing current.
  defp broadcast_lobby(state) do
    broadcast(
      state.id,
      {:lobby,
       %{
         players: Session.names(state.session),
         host: state.host,
         max_ammo: state.max_ammo,
         max_chances: state.max_chances,
         theme: state.theme,
         pace: state.pace,
         mode: state.mode,
         public: state.public
       }}
    )

    sync_presence(state)
  end

  # Mirror this room's public summary into the lobby directory (`DeadGiveaway.Presence`
  # on the "lobbies" topic, issue #43) so the home page can list and join it. Tracks on
  # the first public sync, updates the meta (player count, theme, in-progress) on later
  # ones, and untracks when the host flips the room private. A closed or crashed room is
  # dropped automatically when its process dies, so nothing here runs on shutdown — and a
  # still-private room never touches Presence at all.
  defp sync_presence(%{public: true, presence_tracked: true} = state) do
    Presence.update(self(), Presence.topic(), state.id, presence_meta(state))
    state
  end

  defp sync_presence(%{public: true} = state) do
    Presence.track(self(), Presence.topic(), state.id, presence_meta(state))
    %{state | presence_tracked: true}
  end

  defp sync_presence(%{presence_tracked: true} = state) do
    Presence.untrack(self(), Presence.topic(), state.id)
    %{state | presence_tracked: false}
  end

  defp sync_presence(state), do: state

  # The summary a browsing player sees for this lobby: its code, host, how many humans
  # are waiting, the theme, and whether a round is currently running (so the home page can
  # badge it in-progress rather than hide it — issue #43).
  defp presence_meta(state) do
    %{
      code: state.id,
      host: state.host,
      players: Session.count(state.session),
      theme: state.theme,
      in_progress: state.world != nil
    }
  end

  # Pull a host-set count (bullets or lives) into the whole-number range [lo, hi],
  # whatever a client sends — out-of-range or non-integer values are clamped back in.
  defp clamp(n, lo, hi) when is_integer(n), do: n |> max(lo) |> min(hi)
  defp clamp(n, lo, hi) when is_number(n), do: clamp(trunc(n), lo, hi)
  defp clamp(_, lo, _), do: lo

  # Keep `theme` a known key; anything else (a stale or hand-crafted client value)
  # falls back to `current` so a bad pick can't leave the room on a missing pack.
  defp validate_theme(theme, current), do: if(Themes.valid?(theme), do: theme, else: current)

  # Accept a pace as an atom (config/tests) or a string (the client sends "slow" etc.),
  # keeping the current pace for anything unknown. Compares against World.paces() by string
  # rather than String.to_atom, so a crafted payload can't mint arbitrary atoms.
  defp validate_pace(pace, _current) when pace in [:slow, :medium, :fast], do: pace

  defp validate_pace(pace, current) when is_binary(pace) do
    Enum.find(World.paces(), current, fn p -> Atom.to_string(p) == pace end)
  end

  defp validate_pace(_pace, current), do: current

  # Same shape as the pace: accept a known mode as an atom or a client string (#53),
  # keep the current mode for anything unknown, and never mint atoms from the wire.
  defp validate_mode(mode, _current) when mode in [:classic, :red_light], do: mode

  defp validate_mode(mode, current) when is_binary(mode) do
    Enum.find(World.modes(), current, fn m -> Atom.to_string(m) == mode end)
  end

  defp validate_mode(_mode, current), do: current

  defp put_unless_nil(opts, _key, nil), do: opts
  defp put_unless_nil(opts, key, value), do: Keyword.put(opts, key, value)
end
