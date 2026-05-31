defmodule DeathRace.Accounts do
  @moduledoc """
  Registered players and their persisted, cumulative wins-only scoreboard
  (DESIGN §8, §10). Guests (unregistered names) are never tracked.
  """

  import Ecto.Query

  alias DeathRace.Repo
  alias DeathRace.Accounts.Player

  @doc "Register a player by (unique) name. Returns `{:ok, player}` or `{:error, changeset}`."
  def register_player(name) do
    %Player{}
    |> Player.registration_changeset(%{name: name})
    |> Repo.insert()
  end

  @doc """
  Atomically credit a win to the registered player `name`. Returns
  `{:ok, player}`, or `:ignored` if no such player exists (a guest — only wins
  matter, and only for the logged-in, §8).
  """
  def record_win(name) do
    {count, players} =
      from(p in Player, where: p.name == ^name, update: [inc: [wins: 1]], select: p)
      |> Repo.update_all([])

    case {count, players} do
      {0, _} -> :ignored
      {_, [player]} -> {:ok, player}
    end
  end

  @doc "Players ranked by cumulative wins, descending (ties broken by name)."
  def leaderboard(limit \\ 100) do
    Player
    |> order_by([p], desc: p.wins, asc: p.name)
    |> limit(^limit)
    |> Repo.all()
  end
end
