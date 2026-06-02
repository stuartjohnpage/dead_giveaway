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

  alias DeadGiveaway.{Themes, World}

  # A round can start with as few as this many players (the rest are bots).
  @min_players 1

  # Bullets-per-round is host-configurable in the lobby; default 1 (DESIGN §5),
  # clamped to this range so a stray client value can't hand out absurd ammo.
  @min_ammo 1
  @max_ammo 6

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
  Join the room's lobby. Returns `{:ok, slot, name}`: the assigned slot and the
  player's name. Pass `nil` to be auto-named `"Player N"` (the default); an
  explicit name is kept but disambiguated if already taken, since the name is
  also the player's identity and two players must never collapse onto one body.
  """
  def join(room, player \\ nil), do: GenServer.call(room, {:join, player})

  @doc "Leave the room, freeing the player's slot so they stop counting toward rounds."
  def leave(room, player), do: GenServer.call(room, {:leave, player})

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
  Set the room's cosmetic theme (`DeadGiveaway.Themes`). Like the bullet count it's a
  host-set lobby knob: an unknown key keeps the current theme, and a change is broadcast
  to everyone's lobby view so all clients swap art/audio together. Ignored mid-round.
  """
  def set_theme(room, theme), do: GenServer.call(room, {:set_theme, theme})

  @doc "Round status: `:waiting` until a round is running, then `:running`."
  def status(room), do: GenServer.call(room, :status)

  @doc "Set a player's movement verb (`:stop | :walk | :run`)."
  def set_verb(room, player, verb), do: GenServer.call(room, {:set_verb, player, verb})

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

  @doc "PubSub topic a client subscribes to for a room's snapshot stream."
  def topic(id), do: "room:#{id}"

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
      bots: Keyword.get(opts, :bots, 0),
      finish_x: Keyword.get(opts, :finish_x),
      # Host-configurable bullets per player per round; defaults to one (DESIGN §5).
      max_ammo: clamp_ammo(Keyword.get(opts, :max_ammo, 1)),
      # Host-configurable cosmetic theme (DESIGN §9); defaults to the catalogue head.
      theme: validate_theme(Keyword.get(opts, :theme, Themes.default()), Themes.default()),
      # Optional persistence sink (a module with `record_win/1`, e.g.
      # DeadGiveaway.Accounts). Off by default so the sim has no DB dependency.
      stats_mod: Keyword.get(opts, :stats),
      tick_ms: tick_ms,
      # Shut an empty room down after this many ms idle so abandoned lobbies (and
      # their codes) don't pile up. `nil` (the default) disables expiry — handy
      # for unit tests that don't want a room vanishing under them.
      empty_after_ms: Keyword.get(opts, :empty_after_ms),
      expire_ref: nil,
      players: %{},
      # Monotonic so a freed slot is never handed out again — reusing a slot key
      # after a `leave` would silently overwrite a still-present player.
      next_slot: 0,
      world: nil,
      scores: %{}
    }

    # The tick timer (if any) runs for the room's lifetime; it idles while no
    # round is in progress, so round resets never double-schedule it.
    if tick_ms, do: schedule_tick(tick_ms)
    {:ok, state}
  end

  @impl true
  def handle_call({:join, player}, _from, state) do
    slot = state.next_slot
    name = player_name(player, slot, state.players)

    # Joining only places you in the lobby — a round starts when someone hits Go.
    # A join means the room is no longer empty, so cancel any pending expiry.
    state =
      %{state | next_slot: slot + 1}
      |> put_in([:players, slot], name)
      |> cancel_expiry()

    broadcast_lobby(state)
    {:reply, {:ok, slot, name}, state}
  end

  def handle_call({:leave, player}, _from, state) do
    players = state.players |> Enum.reject(fn {_slot, name} -> name == player end) |> Map.new()
    # If that was the last player, start the countdown to shut the room down.
    state = %{state | players: players} |> maybe_schedule_expiry()
    broadcast_lobby(state)
    {:reply, :ok, state}
  end

  def handle_call(:close, _from, state) do
    # Notify the room (the closing host included) before we go, so every client
    # navigates home rather than sitting on a lobby whose process is gone.
    broadcast(state.id, :closed)
    {:stop, :normal, :ok, state}
  end

  def handle_call(:go, _from, %{world: nil} = state) do
    state = if map_size(state.players) >= @min_players, do: start_round(state), else: state
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
    state = %{state | max_ammo: clamp_ammo(n)}
    broadcast_lobby(state)
    {:reply, :ok, state}
  end

  def handle_call({:set_max_ammo, _n}, _from, state), do: {:reply, :ok, state}

  # Theme is cosmetic and reloaded client-side, so it only changes between rounds —
  # a live round keeps the look it started with rather than swapping mid-race.
  def handle_call({:set_theme, theme}, _from, %{world: nil} = state) do
    state = %{state | theme: validate_theme(theme, state.theme)}
    broadcast_lobby(state)
    {:reply, :ok, state}
  end

  def handle_call({:set_theme, _theme}, _from, state), do: {:reply, :ok, state}

  def handle_call({:set_verb, player, verb}, _from, state) do
    {:reply, :ok, update_world(state, &state.world_mod.set_verb(&1, player, verb))}
  end

  def handle_call({:fire, _player, _crosshair}, _from, %{world: nil} = state) do
    {:reply, :no_shot, state}
  end

  def handle_call({:fire, player, crosshair}, _from, state) do
    {world, event} = state.world_mod.fire(state.world, player, crosshair)
    # The world resolves *which body* dies (it ghosts in the next snapshot), but
    # we never surface whether it was human or bot — to the shooter or anyone
    # else. A shot is a pure gamble (DESIGN §5).
    spent? = match?({:killed, _}, event)

    # A spent bullet cracks out a shot everyone in the room hears, but the
    # broadcast stays anonymous — no shooter, position, or outcome — so firing
    # still tells no one anything (DESIGN §5).
    if spent?, do: broadcast(state.id, :shot)

    {:reply, if(spent?, do: :fired, else: :no_shot), %{state | world: world}}
  end

  def handle_call(:tick, _from, state) do
    {state, snapshot} = do_tick(state)
    {:reply, {:ok, snapshot}, state}
  end

  def handle_call({:score, player}, _from, state) do
    {:reply, Map.get(state.scores, player, 0), state}
  end

  @impl true
  def handle_info(:tick, state) do
    {state, _snapshot} = do_tick(state)
    schedule_tick(state.tick_ms)
    {:noreply, state}
  end

  # The empty-room countdown elapsed. Stop only if still empty — a player may
  # have rejoined and cancelled the timer just as it fired (the message can
  # already be in the mailbox), in which case we stand down.
  def handle_info(:expire, %{players: players} = state) when map_size(players) == 0 do
    {:stop, :normal, state}
  end

  def handle_info(:expire, state), do: {:noreply, %{state | expire_ref: nil}}

  # --- Internals ---

  # No name given → auto-name by slot ("Player 1", "Player 2", …). An explicit
  # name is kept, but disambiguated since the name is also the player's identity
  # and two players must never collapse onto one body/bullet.
  defp player_name(nil, slot, _players), do: "Player #{slot + 1}"
  defp player_name(name, _slot, players), do: uniquify(name, players)

  defp uniquify(name, players) do
    taken = MapSet.new(Map.values(players))

    if MapSet.member?(taken, name) do
      Stream.iterate(2, &(&1 + 1))
      |> Stream.map(&"#{name} (#{&1})")
      |> Enum.find(&(not MapSet.member?(taken, &1)))
    else
      name
    end
  end

  defp start_round(state) do
    opts =
      [
        seed: state.seed,
        humans: Map.values(state.players),
        bots: state.bots,
        max_ammo: state.max_ammo
      ]
      |> put_unless_nil(:finish_x, state.finish_x)

    # Tell clients the round is live so they can clear the lobby and re-arm.
    broadcast(state.id, :round_start)
    %{state | world: state.world_mod.new(opts)}
  end

  # Advance one tick: step the world, broadcast the snapshot, and on a finish
  # award the win and reset for the next round.
  defp do_tick(%{world: nil} = state), do: {state, nil}

  defp do_tick(state) do
    world = state.world_mod.tick(state.world)
    snapshot = state.world_mod.snapshot(world)
    broadcast(state.id, {:snapshot, snapshot})
    state = %{state | world: world}

    state = if state.world_mod.finished?(world), do: finish_round(state), else: state
    {state, snapshot}
  end

  defp finish_round(state) do
    outcome = state.world_mod.outcome(state.world)
    # Award first so the broadcast carries the up-to-date session scoreboard.
    state = award(state, outcome)
    broadcast(state.id, {:round_over, outcome, scoreboard(state)})
    reset_round(state)
  end

  defp award(state, {:winner, player}) do
    # Persist the win for registered players (guests are ignored by the sink).
    if state.stats_mod, do: state.stats_mod.record_win(player)
    update_in(state.scores[player], &((&1 || 0) + 1))
  end

  # A bot crossing first (the sim's `:wash`) credits the shared Bot tally — bots
  # are one opponent on the board. Not persisted (no player stat behind it).
  defp award(state, :wash), do: update_in(state.scores[@bot_name], &((&1 || 0) + 1))

  defp award(state, _outcome), do: state

  # The standings shown between rounds: every current player next to their win
  # count (0 if they've yet to finish first), plus the shared Bot tally. Built
  # from the live roster so the board reads like the lobby list, not just winners.
  defp scoreboard(state) do
    for name <- [@bot_name | Map.values(state.players)], into: %{} do
      {name, Map.get(state.scores, name, 0)}
    end
  end

  # Drop back to the lobby: re-seed and tear down the world. The next round
  # won't start until a player hits Go (§8).
  defp reset_round(state) do
    state = %{state | seed: state.seed + 1, world: nil}
    broadcast_lobby(state)
    state
  end

  defp update_world(%{world: nil} = state, _fun), do: state
  defp update_world(state, fun), do: %{state | world: fun.(state.world)}

  defp schedule_tick(tick_ms), do: Process.send_after(self(), :tick, tick_ms)

  # Arm the shutdown timer when the room empties (no-op if expiry is disabled or
  # the room still has players). Always clears any prior timer first so leaves
  # can't stack up multiple pending expiries.
  defp maybe_schedule_expiry(%{empty_after_ms: nil} = state), do: state

  defp maybe_schedule_expiry(%{players: players} = state) when map_size(players) > 0,
    do: state

  defp maybe_schedule_expiry(state) do
    state = cancel_expiry(state)
    %{state | expire_ref: Process.send_after(self(), :expire, state.empty_after_ms)}
  end

  defp cancel_expiry(%{expire_ref: nil} = state), do: state

  defp cancel_expiry(%{expire_ref: ref} = state) do
    Process.cancel_timer(ref)
    %{state | expire_ref: nil}
  end

  defp broadcast(id, message) do
    Phoenix.PubSub.broadcast(DeadGiveaway.PubSub, topic(id), message)
  end

  # The lobby roster — who's currently waiting to play — plus the room config the
  # lobby UI reflects (the host-set bullet count and theme).
  defp broadcast_lobby(state) do
    broadcast(
      state.id,
      {:lobby,
       %{players: Map.values(state.players), max_ammo: state.max_ammo, theme: state.theme}}
    )
  end

  # Keep bullets-per-round a whole number in [@min_ammo, @max_ammo], whatever a
  # client sends — out-of-range or non-integer values are pulled back into bounds.
  defp clamp_ammo(n) when is_integer(n), do: n |> max(@min_ammo) |> min(@max_ammo)
  defp clamp_ammo(n) when is_number(n), do: clamp_ammo(trunc(n))
  defp clamp_ammo(_), do: @min_ammo

  # Keep `theme` a known key; anything else (a stale or hand-crafted client value)
  # falls back to `current` so a bad pick can't leave the room on a missing pack.
  defp validate_theme(theme, current), do: if(Themes.valid?(theme), do: theme, else: current)

  defp put_unless_nil(opts, _key, nil), do: opts
  defp put_unless_nil(opts, key, value), do: Keyword.put(opts, key, value)
end
