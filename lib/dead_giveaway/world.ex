defmodule DeadGiveaway.World do
  @moduledoc """
  The authoritative, *pure* Dead Giveaway simulation (DESIGN §9).

  `new/1 → tick/1 → snapshot/1` are plain functions: world state in, world state
  out, no processes. All randomness is driven by an injected `:seed` so a given
  seed always produces the same world — which is what makes the sim testable.

  The human/bot mapping is private to the world. `snapshot/1` (the only thing a
  client ever sees) never reveals which entities are human (DESIGN §2, §9).
  """

  defstruct entities: %{},
            finish_x: 1000.0,
            rng: nil,
            slot_of: %{},
            max_ammo: 1,
            shots: %{},
            chances: %{},
            # {move_ticks, stop_ticks} ranges for this round's pace (#17).
            pace_ticks: nil

  # Movement speeds, in world units per tick (dev values).
  @walk_speed 1.25
  @run_speed 2.5
  # A moving bot moves at exactly the human walk speed, so pace never tells a
  # walking human apart from a moving bot — only *running* (faster than any bot
  # can ever move) is a hard tell (DESIGN §3, §6).
  @bot_speed @walk_speed

  # Each bot cycles move → stop → move on its OWN timing, with the duration of
  # each phase re-rolled when it begins. That desynchronises the crowd (no
  # waves, no jiggle) and the stop phases keep overall progress in check (§4).
  #
  # Pace (#17) is the lobby-leader's round-tempo dial: it sets the bot move:stop tick
  # ranges, i.e. how much of the time the crowd spends MOVING — NOT how fast a moving
  # body goes. @bot_speed stays pinned to @walk_speed regardless, so a moving bot always
  # looks exactly like a walking human (DESIGN §3/§6); pace can never become a tell. A
  # lower move:stop ratio = less ground covered per tick = a slower race overall. Approx
  # share of time moving: fast ~40%, medium ~30%, slow ~20%. Tuned by feel — `fast` is the
  # original tempo. `:fast` is the default (and the fallback for an unknown value).
  @pace_ticks %{
    fast: {12..28, 18..40},
    medium: {12..28, 30..60},
    slow: {10..22, 45..80}
  }
  @default_pace :fast

  # Vertical distance between adjacent rows, so the crosshair (a continuous x/y
  # point) can pick the nearest body across rows.
  @row_spacing 10.0

  # How close (world units) the crosshair must be to a body for the shot to connect
  # (#12). A shot lands on the nearest living body only within this radius; a click into
  # empty space misses — the bullet's still spent, but no one drops. This is what stops
  # the old "every shot kills the nearest body" magnetism: aim now has to be on a body
  # ("click them, they drop") and can whiff ("oh, missed"). A touch under the ~10-unit row
  # spacing, so you must click roughly on a body rather than snap to a far one. Tuned by
  # feel — bump it up if shots feel too fiddly, down if aim still feels too forgiving.
  @hit_radius 7.0

  def walk_speed, do: @walk_speed
  def run_speed, do: @run_speed
  # The fastest a bot ever moves (it walks or stands still — never runs).
  def bot_max_speed, do: @bot_speed
  def row_spacing, do: @row_spacing

  @doc "The valid pace keys (#17), so callers validate against one source of truth."
  def paces, do: Map.keys(@pace_ticks)
  @doc "The default pace when none (or an unknown one) is given."
  def default_pace, do: @default_pace

  @doc """
  Build a fresh world. Options:

    * `:seed`   — integer seed for all randomness (required for determinism)
    * `:humans` — list of player ids that occupy human entities
    * `:bots`   — number of bot entities to fill in
    * `:finish_x` — finish line x (default 1000.0)
    * `:max_ammo` — bullets each player gets for the round (default 1)
    * `:max_chances` — lives each player gets for the round (default 1, i.e. one
      life: when your body drops you're out. >1 lets you take over a free bot body
      on death instead, spending a life — DESIGN §7)
    * `:pace` — round tempo `:slow | :medium | :fast` (#17), setting the bot move:stop
      ratio (default `:fast`, the original tempo; an unknown value falls back to it)
  """
  def new(opts) do
    seed = Keyword.fetch!(opts, :seed)
    humans = Keyword.get(opts, :humans, [])
    bot_count = Keyword.get(opts, :bots, 0)
    finish_x = Keyword.get(opts, :finish_x, 1000.0)
    max_ammo = Keyword.get(opts, :max_ammo, 1)
    max_chances = Keyword.get(opts, :max_chances, 1)

    pace_ticks =
      Map.get(@pace_ticks, Keyword.get(opts, :pace, @default_pace), @pace_ticks[@default_pace])

    total = length(humans) + bot_count
    rng = :rand.seed_s(:exsss, {seed, seed, seed})

    # One row per character. Guard the empty case explicitly: `0..(total - 1)`
    # with total == 0 is the decreasing range `0..-1` (i.e. `[0, -1]`), which
    # would spawn phantom rows — so a world with no characters has no rows.
    rows = if total == 0, do: [], else: Enum.to_list(0..(total - 1))

    # Randomly choose which rows the humans occupy so identity isn't positional.
    {human_rows, rng} = take_random(rows, length(humans), rng)
    human_row_to_player = Enum.zip(human_rows, humans) |> Map.new()

    entities =
      for row <- rows, into: %{} do
        player = Map.get(human_row_to_player, row)
        {row, new_entity(row, player)}
      end

    slot_of = for {row, p} <- human_row_to_player, into: %{}, do: {p, row}

    # Give each bot a random starting phase so the crowd is already desynced on
    # tick 1 rather than all flipping move/stop together.
    {entities, rng} = seed_bot_phases(entities, pace_ticks, rng)

    # Every human starts the round with `max_chances` lives (DESIGN §7).
    chances = for p <- humans, into: %{}, do: {p, max_chances}

    %__MODULE__{
      entities: entities,
      finish_x: finish_x,
      rng: rng,
      slot_of: slot_of,
      max_ammo: max_ammo,
      chances: chances,
      pace_ticks: pace_ticks
    }
  end

  @doc """
  Set a human player's movement verb (`:stop | :walk | :run`). `:run` is a
  human-only capability — no bot ever runs, which is what makes it a hard tell
  (DESIGN §3, §6). Applied on the next `tick/1`.
  """
  def set_verb(%__MODULE__{} = world, player, verb) when verb in [:stop, :walk, :run] do
    # A player not in this round's world (e.g. a mid-round joiner who spectates
    # until next round, §8) has no body to drive — ignore their input rather
    # than crash, mirroring how `fire/3` answers `:no_shot` for the same case.
    case Map.fetch(world.slot_of, player) do
      {:ok, row} -> update_in(world.entities[row], &%{&1 | verb: verb, speed: speed_for(verb)})
      :error -> world
    end
  end

  @doc "Advance the simulation by one tick."
  def tick(%__MODULE__{} = world) do
    {entities, rng} =
      world.entities
      |> Enum.sort_by(fn {row, _} -> row end)
      |> Enum.reduce({%{}, world.rng}, fn {row, e}, {acc, rng} ->
        {e, rng} = step_entity(e, world.pace_ticks, rng)
        {Map.put(acc, row, e), rng}
      end)

    %{world | entities: entities, rng: rng}
  end

  @doc """
  Fire one of `player`'s bullets at crosshair point `{x, y}` (DESIGN §5).

  Hitscan with a hit radius (#12): kills the living character nearest the crosshair —
  which may be the shooter's own body — but only if one is within `@hit_radius`. Returns
  `{world, :killed}` when a body drops, `{world, :spent}` when the bullet's spent on empty
  air (a miss — aim was off, or nothing's in range), or `{world, :no_shot}` if the player
  is out of ammo or already out. A killed and a missed shot both consume a bullet; only
  `:no_shot` doesn't. Each player gets `max_ammo` bullets per round (default 1).

  A kill reveals *nothing* — not who fired, nor whether the body was a human or a
  bot (DESIGN §5). The bare `:killed` says only "a bullet was spent"; the caller
  learns no more than that, and the dropped body simply ghosts in the next
  snapshot. Whether the *owner* of a dropped body is now out (vs. taken over a bot
  body, §7) is found by querying `player_alive?/2`, not from this return value, so
  the knock-out signal stays a private server detail and never rides a broadcast.
  """
  def fire(%__MODULE__{} = world, player, {_cx, _cy} = crosshair) do
    cond do
      ammo_left(world, player) <= 0 -> {world, :no_shot}
      not player_alive?(world, player) -> {world, :no_shot}
      true -> resolve_shot(world, player, crosshair)
    end
  end

  @doc "Bullets `player` has left this round — their `max_ammo` minus shots fired."
  def ammo_left(%__MODULE__{} = world, player) do
    world.max_ammo - Map.get(world.shots, player, 0)
  end

  @doc """
  Lives `player` has left this round (DESIGN §7). Starts at `max_chances`; each body
  they lose to a bot-takeover spends one. At one life left, the next drop puts them
  out. A player not in this round has none. Like `player_alive?/2` this is a private
  server query for the owner's HUD — never part of the public snapshot.
  """
  def chances_left(%__MODULE__{} = world, player) do
    Map.get(world.chances, player, 0)
  end

  @doc """
  Whether `player` should show a public crosshair: they're in this round and still
  hold a bullet. Spending the last shot drops the reticle so everyone sees they're
  now unarmed (DESIGN §5).

  Deliberately *not* gated on the body being alive: a reticle vanishing the instant a
  body dropped would betray that body as a (human) shooter's, and a kill must reveal
  nothing — not who fired, nor whether the body was human or bot (DESIGN §5).
  """
  def armed?(%__MODULE__{} = world, player) do
    Map.has_key?(world.slot_of, player) and ammo_left(world, player) > 0
  end

  @doc "True once any living character has crossed the finish line."
  def finished?(%__MODULE__{} = world), do: crossers(world) != []

  @doc """
  Round outcome (DESIGN §7):

    * `:none`             — nobody has crossed yet
    * `{:winner, player}` — a human crossed first → that human wins
    * `:wash`             — a bot crossed first → no winner, round resets

  When several cross on the same tick, the one furthest past the line is first.
  """
  def outcome(%__MODULE__{} = world) do
    case leader_past_line(world) do
      nil -> :none
      %{human?: true, player: player} -> {:winner, player}
      %{human?: false} -> :wash
    end
  end

  @doc "Public view of the world. Never leaks the human/bot mapping."
  def snapshot(%__MODULE__{} = world) do
    entities =
      world.entities
      |> Map.values()
      |> Enum.sort_by(& &1.id)
      |> Enum.map(&%{id: &1.id, row: &1.row, x: &1.x, verb: &1.verb, alive: &1.alive})

    %{entities: entities, finish_x: world.finish_x}
  end

  # --- Internals ---

  defp new_entity(row, player) do
    %{
      id: row,
      row: row,
      x: 0.0,
      speed: 0.0,
      verb: :stop,
      alive: true,
      human?: player != nil,
      player: player,
      # Bot move/stop cycle state (unused for humans, who move by their verb).
      phase: :stopped,
      phase_left: 0
    }
  end

  defp speed_for(:stop), do: 0.0
  defp speed_for(:walk), do: @walk_speed
  defp speed_for(:run), do: @run_speed

  defp resolve_shot(world, player, crosshair) do
    # The bullet is spent whichever way this goes — a miss costs you the shot too (#12).
    world = Map.update!(world, :shots, &Map.update(&1, player, 1, fn n -> n + 1 end))

    case nearest_living(world, crosshair) do
      {target, dist2} when dist2 <= @hit_radius * @hit_radius ->
        world =
          world
          |> put_in([Access.key(:entities), target.row, :alive], false)
          |> maybe_takeover(target)

        {world, :killed}

      _ ->
        # Out of range of any body (or none left to hit) — the shot cracks out over empty
        # ground. Nothing drops, so the shooter sees their aim whiffed; everyone still
        # hears the (anonymous) report, exactly as for a hit (DESIGN §5).
        {world, :spent}
    end
  end

  # When a *human's* body drops, spend one of their lives to slip into a free bot body
  # instead of being knocked out — provided they have a life to spare (more than the one
  # just lost) and a living bot is free to inhabit (DESIGN §7). With the default of one
  # life this never fires: the body just drops and the owner is out, exactly as before.
  # A life is spent only when the takeover actually happens; with no free body the owner
  # is simply out. The handoff is invisible to peers — the snapshot never says who
  # controls a body, and the owner keeps the same (anonymous) crosshair (DESIGN §5).
  defp maybe_takeover(world, %{human?: true, player: player}) when is_binary(player) do
    lives = chances_left(world, player)

    case lives > 1 and free_bot(world) do
      %{row: row} ->
        world
        |> put_in([Access.key(:chances), player], lives - 1)
        |> inhabit(player, row)

      _ ->
        world
    end
  end

  # A bot's body dropping costs no player a life — nothing to do.
  defp maybe_takeover(world, _target), do: world

  # Move `player` into the bot body at `row`: that body becomes human-driven (idle until
  # they pick it up, since they don't yet know it's theirs), the old body stays a corpse,
  # and `slot_of` now points at the new row so input/fire/aim follow them there.
  defp inhabit(world, player, row) do
    old_row = world.slot_of[player]

    world
    |> put_in([Access.key(:entities), old_row, :player], nil)
    |> put_in([Access.key(:entities), old_row, :human?], false)
    |> update_in(
      [Access.key(:entities), row],
      &%{&1 | human?: true, player: player, verb: :stop, speed: 0.0}
    )
    |> put_in([Access.key(:slot_of), player], row)
  end

  # Which free body a respawning player inherits: the living bot furthest back (smallest
  # x). The rule is deliberate — it's deterministic (no rng, so the sim stays replayable),
  # leaks nothing (a body's controller is never in the snapshot, §5), and re-enters you at
  # the back of the pack, a fair cost for cheating death. `nil` if every other character is
  # a human or already down — with no free body you're simply out (DESIGN §7).
  defp free_bot(world) do
    world.entities
    |> Map.values()
    |> Enum.filter(&(&1.alive and not &1.human?))
    |> case do
      [] -> nil
      bots -> Enum.min_by(bots, & &1.x)
    end
  end

  @doc """
  Whether `player`'s body is still standing this round — `false` if they've been
  shot out or aren't in this round at all.

  This is how the Room learns a player has been knocked out (their body dropped and,
  with no chance/takeover left, they're out for the round, §7) so it can tell *that
  owner privately*. It is deliberately a server-side query, never part of the public
  snapshot: a body dropping reveals nothing about whose it was (DESIGN §5), so the
  "you're out" signal must be routed to the owner alone, not inferred by peers.
  """
  def player_alive?(%__MODULE__{} = world, player) do
    case Map.fetch(world.slot_of, player) do
      {:ok, row} -> world.entities[row].alive
      :error -> false
    end
  end

  # The nearest living body to the crosshair as `{entity, squared_distance}`, or `nil` if
  # nothing's left alive. The caller compares the distance against @hit_radius — squared on
  # both sides, so no sqrt.
  defp nearest_living(world, {cx, cy}) do
    world.entities
    |> Map.values()
    |> Enum.filter(& &1.alive)
    |> Enum.map(fn e ->
      dx = e.x - cx
      dy = e.row * @row_spacing - cy
      {e, dx * dx + dy * dy}
    end)
    |> case do
      [] -> nil
      scored -> Enum.min_by(scored, &elem(&1, 1))
    end
  end

  # Dead characters are out for the round — frozen, can't win, can't be re-shot.
  defp step_entity(%{alive: false} = e, _ticks, rng), do: {e, rng}

  # Humans move by their player-set verb; their verb is never auto-changed.
  defp step_entity(%{human?: true} = e, _ticks, rng), do: {advance(e), rng}

  # A bot counts down its current phase; when it elapses it flips move↔stop and
  # rolls a fresh duration (from this round's pace ranges) for the new phase. Steady
  # speed within a phase = no jiggle; per-bot durations = a desynced crowd. A bot never
  # runs (§4).
  defp step_entity(%{human?: false} = e, ticks, rng) do
    {e, rng} = advance_phase(e, ticks, rng)
    {advance(e), rng}
  end

  defp advance_phase(%{phase_left: n} = e, _ticks, rng) when n > 1 do
    {%{e | phase_left: n - 1}, rng}
  end

  defp advance_phase(e, ticks, rng) do
    next = if e.phase == :moving, do: :stopped, else: :moving
    {phase_left, rng} = roll_phase_ticks(next, ticks, rng)
    {set_phase(e, next, phase_left), rng}
  end

  defp set_phase(e, :moving, phase_left),
    do: %{e | phase: :moving, phase_left: phase_left, verb: :walk, speed: @bot_speed}

  defp set_phase(e, :stopped, phase_left),
    do: %{e | phase: :stopped, phase_left: phase_left, verb: :stop, speed: 0.0}

  defp roll_phase_ticks(:moving, {move_ticks, _stop_ticks}, rng), do: roll_in(move_ticks, rng)
  defp roll_phase_ticks(:stopped, {_move_ticks, stop_ticks}, rng), do: roll_in(stop_ticks, rng)

  defp roll_in(min..max//_, rng) do
    {i, rng} = :rand.uniform_s(max - min + 1, rng)
    {min + i - 1, rng}
  end

  # Seed each bot mid-cycle with a random phase + duration so the field starts
  # desynchronised (humans keep the default idle phase, which they never use).
  defp seed_bot_phases(entities, ticks, rng) do
    Enum.reduce(entities, {%{}, rng}, fn
      {row, %{human?: true} = e}, {acc, rng} ->
        {Map.put(acc, row, e), rng}

      {row, e}, {acc, rng} ->
        {roll, rng} = :rand.uniform_s(rng)
        phase = if roll < 0.5, do: :moving, else: :stopped
        {phase_left, rng} = roll_phase_ticks(phase, ticks, rng)
        {Map.put(acc, row, set_phase(e, phase, phase_left)), rng}
    end)
  end

  defp advance(%{verb: :stop} = e), do: e
  defp advance(e), do: %{e | x: e.x + e.speed}

  defp crossers(world) do
    world.entities
    |> Map.values()
    |> Enum.filter(&(&1.alive and &1.x >= world.finish_x))
  end

  defp leader_past_line(world) do
    case crossers(world) do
      [] -> nil
      list -> Enum.max_by(list, & &1.x)
    end
  end

  # Pull `n` random elements out of `list`, threading the rng state.
  defp take_random(list, n, rng), do: take_random(list, n, rng, [])
  defp take_random(_list, 0, rng, acc), do: {acc, rng}

  defp take_random(list, n, rng, acc) do
    {idx, rng} = :rand.uniform_s(length(list), rng)
    {picked, rest} = List.pop_at(list, idx - 1)
    take_random(rest, n - 1, rng, [picked | acc])
  end
end
