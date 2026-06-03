defmodule DeadGiveaway.Session do
  @moduledoc """
  Pure lobby-and-scoreboard core for a room: the monotonic-slot roster, name
  assignment/uniquification, and the cumulative per-category scoreboard. No
  process, no PubSub, no DB — a plain struct threaded through `Room`'s state.

  `Room` keeps a single `:session` field in place of the old `players` /
  `next_slot` / `scores` trio, and routes every roster read/write and every
  scoring decision through here. The side effects that used to sit beside this
  logic — broadcasting, the empty-room timer, the `stats_mod.record_win/1`
  persistence sink — stay in `Room`; this module only moves the pure tally and
  the roster bookkeeping.

  ## Extension seams (latent, not built)

  Three knobs are open-for-extension but default to today's exact behaviour, so
  a default `Session` is byte-for-byte the old Room logic with zero external
  dependency:

    * `bot_name` — the shared opponent's scoreboard label (default `"Bot"`).
    * `namer` — the `(given, slot, taken) -> name` naming policy (default:
      blank → lowest-free `"Player N"`, explicit collision → `"name (2)"`).
    * `clock` — stamps `Player.joined_at` (default: the monotonic clock).

  The per-category `scores` map likewise keeps the door open for boards beyond
  `:wins` (e.g. a "most accurate shooter" `:kills` tally via `credit/4` +
  `scoreboard/2`). None of these are wired to a feature yet — they are
  interface shape, not work items.
  """

  alias __MODULE__.Player

  @type slot :: non_neg_integer()
  @type name :: String.t()
  @type points :: non_neg_integer()
  # MVP awards only `:wins`; the map keeps the category dimension open.
  @type category :: atom()
  @type outcome :: {:winner, name()} | :wash | term()

  defmodule Player do
    @moduledoc "A roster entry: the monotonic slot, the assigned name, a join stamp."
    @type t :: %__MODULE__{
            slot: DeadGiveaway.Session.slot(),
            name: DeadGiveaway.Session.name(),
            joined_at: integer()
          }
    defstruct [:slot, :name, :joined_at]
  end

  @type namer :: (name() | nil, slot(), [name()] -> name())
  @type clock :: (-> integer())

  @type t :: %__MODULE__{
          players: %{slot() => Player.t()},
          next_slot: slot(),
          scores: %{name() => %{category() => points()}},
          bot_name: name(),
          namer: namer(),
          clock: clock()
        }

  # The seam fields default to today's exact behaviour here in the struct (not only in
  # new/1), so even a bare `%Session{}` literal is fully wired and join/2 can't hit a nil
  # namer/clock. Remote captures, so they resolve at runtime (no forward-reference issue).
  defstruct players: %{},
            next_slot: 0,
            scores: %{},
            bot_name: "Bot",
            namer: &__MODULE__.default_namer/3,
            clock: &System.monotonic_time/0

  @doc """
  A fresh, empty session. Every option defaults to today's behaviour: the `"Bot"`
  opponent label, the lowest-free `"Player N"` / collision-disambiguating namer,
  and the monotonic clock — so `new/0` has no external dependency. Unprovided options
  fall back to the struct defaults above.
  """
  @spec new(keyword()) :: t()
  def new(opts \\ []) do
    struct(__MODULE__, Keyword.take(opts, [:bot_name, :namer, :clock]))
  end

  # --- Roster mutation ---

  @doc """
  Seat a player and return `{slot, assigned_name, session}`. The slot is the
  monotonic `next_slot` — a freed slot is never handed out again, so a `leave`
  can't silently overwrite a still-present player. `nil` is auto-named
  `"Player N"` (the lowest free number, so a number a leaver frees is reused
  rather than the count climbing); an explicit name is kept but disambiguated to
  `"name (2)"`, `"name (3)"`, … if already taken, since the name is also the
  player's identity and two players must never collapse onto one body.
  """
  @spec join(t(), name() | nil) :: {slot(), name(), t()}
  def join(%__MODULE__{} = session, given \\ nil) do
    slot = session.next_slot
    name = session.namer.(given, slot, names(session))
    player = %Player{slot: slot, name: name, joined_at: session.clock.()}

    session = %{
      session
      | players: Map.put(session.players, slot, player),
        next_slot: slot + 1
    }

    {slot, name, session}
  end

  @doc """
  Remove the player with this name, retiring their slot (never reissued) and
  dropping their score tally — names are reused, so a lingering score would be
  inherited by whoever next takes the freed name. The shared bot tally isn't a
  player, so it's left untouched.
  """
  @spec leave(t(), name()) :: t()
  def leave(%__MODULE__{} = session, name) do
    players = session.players |> Enum.reject(fn {_slot, p} -> p.name == name end) |> Map.new()
    %{session | players: players, scores: Map.delete(session.scores, name)}
  end

  # --- Roster queries ---

  @doc "Names of everyone seated, in slot order (the lobby roster / `World.new` humans list)."
  @spec names(t()) :: [name()]
  def names(%__MODULE__{} = session), do: session |> players() |> Enum.map(& &1.name)

  @doc "Every seated player, in slot order (earliest joiner first)."
  @spec players(t()) :: [Player.t()]
  def players(%__MODULE__{} = session) do
    # Explicitly slot-sorted. Room previously shipped `Map.values/1` of a `%{slot => name}`
    # map; for the ≤32 entries a real lobby ever holds, Erlang's small-map order is already
    # slot order, so this is identical in practice — and a deliberate tightening above that
    # (a >32-player room had hash-ordered, non-deterministic values), which seeds World.new's
    # body assignment, so a stable slot order is the safe choice.
    session.players |> Map.values() |> Enum.sort_by(& &1.slot)
  end

  @doc "How many players are seated."
  @spec count(t()) :: non_neg_integer()
  def count(%__MODULE__{} = session), do: map_size(session.players)

  @doc "Whether the lobby is empty (drives the room's empty-expiry timer)."
  @spec empty?(t()) :: boolean()
  def empty?(%__MODULE__{} = session), do: count(session) == 0

  @doc "Whether a name is currently seated."
  @spec member?(t(), name()) :: boolean()
  def member?(%__MODULE__{} = session, name), do: name in names(session)

  @doc "The player at a slot, or `nil` if it's free/retired."
  @spec player_at(t(), slot()) :: Player.t() | nil
  def player_at(%__MODULE__{} = session, slot), do: Map.get(session.players, slot)

  # --- Scoring ---

  @doc """
  Apply a round outcome to the scoreboard: `{:winner, name}` credits that player
  one win; `:wash` (a bot crossing first) credits the shared bot tally; any other
  outcome is a no-op. The persistence side effect for a human win stays in `Room`.
  """
  @spec award(t(), outcome()) :: t()
  def award(%__MODULE__{} = session, {:winner, name}), do: credit(session, name, :wins, 1)
  def award(%__MODULE__{} = session, :wash), do: credit(session, session.bot_name, :wins, 1)
  def award(%__MODULE__{} = session, _outcome), do: session

  @doc """
  The lower-level primitive `award/2` is built on: add `points` to `name`'s tally
  in `category`, creating either key as needed. Opens the door to boards beyond
  `:wins` without changing `award/2`'s outcome routing.
  """
  @spec credit(t(), name(), category(), points()) :: t()
  def credit(%__MODULE__{} = session, name, category, points) do
    cats = session.scores |> Map.get(name, %{}) |> Map.update(category, points, &(&1 + points))
    %{session | scores: Map.put(session.scores, name, cats)}
  end

  @doc "A player's points in a category (default `:wins`); 0 if they've none."
  @spec score(t(), name(), category()) :: points()
  def score(%__MODULE__{} = session, name, category \\ :wins) do
    session.scores |> Map.get(name, %{}) |> Map.get(category, 0)
  end

  @doc """
  The standings shown between rounds: every current player next to their points
  in `category` (0 if they've yet to score), plus the shared bot tally. Built
  from the live roster so the board reads like the lobby list, not just winners.
  """
  @spec scoreboard(t(), category()) :: %{name() => points()}
  def scoreboard(%__MODULE__{} = session, category \\ :wins) do
    for name <- [session.bot_name | names(session)], into: %{} do
      {name, score(session, name, category)}
    end
  end

  @doc "The shared bot opponent's scoreboard label."
  @spec bot_name(t()) :: name()
  def bot_name(%__MODULE__{} = session), do: session.bot_name

  # --- Default seams (today's exact behaviour) ---

  @doc false
  # The default naming policy. Public only so the `namer` struct default can capture it
  # remotely (`&__MODULE__.default_namer/3`); not part of the intended API — go through
  # join/2. No name → the lowest free "Player N"; an explicit name kept unless taken, then
  # "name (2)", "name (3)", … — the first number that isn't already in use.
  def default_namer(nil, _slot, taken) do
    Stream.iterate(1, &(&1 + 1))
    |> Stream.map(&"Player #{&1}")
    |> Enum.find(&(&1 not in taken))
  end

  def default_namer(name, _slot, taken) do
    if name in taken do
      Stream.iterate(2, &(&1 + 1))
      |> Stream.map(&"#{name} (#{&1})")
      |> Enum.find(&(&1 not in taken))
    else
      name
    end
  end
end
