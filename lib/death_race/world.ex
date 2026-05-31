defmodule DeathRace.World do
  @moduledoc """
  The authoritative, *pure* Death Race simulation (DESIGN §9).

  `new/1 → tick/1 → snapshot/1` are plain functions: world state in, world state
  out, no processes. All randomness is driven by an injected `:seed` so a given
  seed always produces the same world — which is what makes the sim testable.

  The human/bot mapping is private to the world. `snapshot/1` (the only thing a
  client ever sees) never reveals which entities are human (DESIGN §2, §9).
  """

  defstruct entities: %{}, finish_x: 1000.0, rng: nil, slot_of: %{}, spent: MapSet.new()

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
  # Tunable: a lower move:stop ratio = less ground covered across the field.
  @bot_move_ticks 12..28
  @bot_stop_ticks 18..40

  # Vertical distance between adjacent rows, so the crosshair (a continuous x/y
  # point) can pick the nearest body across rows.
  @row_spacing 10.0

  def walk_speed, do: @walk_speed
  def run_speed, do: @run_speed
  # The fastest a bot ever moves (it walks or stands still — never runs).
  def bot_max_speed, do: @bot_speed
  def row_spacing, do: @row_spacing

  @doc """
  Build a fresh world. Options:

    * `:seed`   — integer seed for all randomness (required for determinism)
    * `:humans` — list of player ids that occupy human entities
    * `:bots`   — number of bot entities to fill in
    * `:finish_x` — finish line x (default 1000.0)
  """
  def new(opts) do
    seed = Keyword.fetch!(opts, :seed)
    humans = Keyword.get(opts, :humans, [])
    bot_count = Keyword.get(opts, :bots, 0)
    finish_x = Keyword.get(opts, :finish_x, 1000.0)

    total = length(humans) + bot_count
    rng = :rand.seed_s(:exsss, {seed, seed, seed})

    # Randomly choose which rows the humans occupy so identity isn't positional.
    {human_rows, rng} = take_random(Enum.to_list(0..(total - 1)), length(humans), rng)
    human_row_to_player = Enum.zip(human_rows, humans) |> Map.new()

    entities =
      for row <- 0..(total - 1), into: %{} do
        player = Map.get(human_row_to_player, row)
        {row, new_entity(row, player)}
      end

    slot_of = for {row, p} <- human_row_to_player, into: %{}, do: {p, row}

    # Give each bot a random starting phase so the crowd is already desynced on
    # tick 1 rather than all flipping move/stop together.
    {entities, rng} = seed_bot_phases(entities, rng)

    %__MODULE__{entities: entities, finish_x: finish_x, rng: rng, slot_of: slot_of}
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
        {e, rng} = step_entity(e, rng)
        {Map.put(acc, row, e), rng}
      end)

    %{world | entities: entities, rng: rng}
  end

  @doc """
  Fire `player`'s single bullet at crosshair point `{x, y}` (DESIGN §5).

  Hitscan: kills the living character nearest the crosshair — which may be the
  shooter's own body. Returns `{world, {:killed, :human | :bot}}` revealing
  player-vs-bot to all, or `{world, :no_shot}` if the player has already fired
  or is already out. One bullet per player per round.
  """
  def fire(%__MODULE__{} = world, player, {_cx, _cy} = crosshair) do
    cond do
      MapSet.member?(world.spent, player) -> {world, :no_shot}
      not player_alive?(world, player) -> {world, :no_shot}
      true -> resolve_shot(world, player, crosshair)
    end
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
    target = nearest_living(world, crosshair)

    world =
      world
      |> put_in([Access.key(:entities), target.row, :alive], false)
      |> Map.update!(:spent, &MapSet.put(&1, player))

    reveal = if target.human?, do: :human, else: :bot
    {world, {:killed, reveal}}
  end

  defp player_alive?(world, player) do
    case Map.fetch(world.slot_of, player) do
      {:ok, row} -> world.entities[row].alive
      :error -> false
    end
  end

  defp nearest_living(world, {cx, cy}) do
    world.entities
    |> Map.values()
    |> Enum.filter(& &1.alive)
    |> Enum.min_by(fn e ->
      dx = e.x - cx
      dy = e.row * @row_spacing - cy
      dx * dx + dy * dy
    end)
  end

  # Dead characters are out for the round — frozen, can't win, can't be re-shot.
  defp step_entity(%{alive: false} = e, rng), do: {e, rng}

  # Humans move by their player-set verb; their verb is never auto-changed.
  defp step_entity(%{human?: true} = e, rng), do: {advance(e), rng}

  # A bot counts down its current phase; when it elapses it flips move↔stop and
  # rolls a fresh duration for the new phase. Steady speed within a phase = no
  # jiggle; per-bot durations = a desynced crowd. A bot never runs (§4).
  defp step_entity(%{human?: false} = e, rng) do
    {e, rng} = advance_phase(e, rng)
    {advance(e), rng}
  end

  defp advance_phase(%{phase_left: n} = e, rng) when n > 1 do
    {%{e | phase_left: n - 1}, rng}
  end

  defp advance_phase(e, rng) do
    next = if e.phase == :moving, do: :stopped, else: :moving
    {phase_left, rng} = roll_phase_ticks(next, rng)
    {set_phase(e, next, phase_left), rng}
  end

  defp set_phase(e, :moving, phase_left),
    do: %{e | phase: :moving, phase_left: phase_left, verb: :walk, speed: @bot_speed}

  defp set_phase(e, :stopped, phase_left),
    do: %{e | phase: :stopped, phase_left: phase_left, verb: :stop, speed: 0.0}

  defp roll_phase_ticks(:moving, rng), do: roll_in(@bot_move_ticks, rng)
  defp roll_phase_ticks(:stopped, rng), do: roll_in(@bot_stop_ticks, rng)

  defp roll_in(min..max//_, rng) do
    {i, rng} = :rand.uniform_s(max - min + 1, rng)
    {min + i - 1, rng}
  end

  # Seed each bot mid-cycle with a random phase + duration so the field starts
  # desynchronised (humans keep the default idle phase, which they never use).
  defp seed_bot_phases(entities, rng) do
    Enum.reduce(entities, {%{}, rng}, fn
      {row, %{human?: true} = e}, {acc, rng} ->
        {Map.put(acc, row, e), rng}

      {row, e}, {acc, rng} ->
        {roll, rng} = :rand.uniform_s(rng)
        phase = if roll < 0.5, do: :moving, else: :stopped
        {phase_left, rng} = roll_phase_ticks(phase, rng)
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
