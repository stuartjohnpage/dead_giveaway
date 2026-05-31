defmodule DeadGiveaway.Rooms do
  @moduledoc """
  Lookup and lifecycle for `DeadGiveaway.Room` processes.

  Rooms are addressed by a string id, started on demand under a
  `DynamicSupervisor`, and registered in a `Registry` so any caller (e.g. a
  joining player's channel) can find the running room for an id.
  """

  alias DeadGiveaway.Room

  @registry DeadGiveaway.RoomRegistry
  @supervisor DeadGiveaway.RoomSupervisor

  @doc """
  Return the room for `id`, starting (and supervising) it if it isn't running
  yet. Idempotent: concurrent or repeated calls for the same id resolve to the
  same process. `opts` are passed to `Room.start_link` on first start.
  """
  def find_or_start(id, opts \\ []) do
    spec = {Room, Keyword.merge([id: id, name: via(id)], opts)}

    case DynamicSupervisor.start_child(@supervisor, spec) do
      {:ok, pid} -> {:ok, pid}
      {:error, {:already_started, pid}} -> {:ok, pid}
      other -> other
    end
  end

  @doc "The pid of the room registered for `id`, or `nil` if none is running."
  def whereis(id) do
    case Registry.lookup(@registry, id) do
      [{pid, _value}] -> pid
      [] -> nil
    end
  end

  defp via(id), do: {:via, Registry, {@registry, id}}
end
