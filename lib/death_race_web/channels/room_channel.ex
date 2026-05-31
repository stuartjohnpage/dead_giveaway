defmodule DeathRaceWeb.RoomChannel do
  @moduledoc """
  Websocket transport for a single Death Race room (DESIGN §9).

  On join the channel finds-or-starts the room, joins the player into the lobby,
  and subscribes to the room's broadcasts. Inbound messages (`input`, `fire`,
  `go`) are routed into the authoritative `Room`; outbound the channel forwards
  the room's `lobby` / `round_start` / `snapshot` / `round_over` broadcasts.
  """

  use Phoenix.Channel

  alias DeathRace.{Room, Rooms}

  # Production room shape; overridable via `config :death_race, :room, ...`
  # (tests use a tiny tick and no bots for determinism).
  @default_room_opts [tick_ms: 50, bots: 24, finish_x: 500.0, stats: DeathRace.Accounts]

  @impl true
  def join("room:" <> id, payload, socket) do
    case resolve_room(id, payload) do
      {:ok, room} ->
        # Subscribe before joining so we receive our own join's lobby roster.
        Phoenix.PubSub.subscribe(DeathRace.PubSub, Room.topic(id))

        # Players are auto-named "Player N" for now; the room returns the canonical
        # name, which is this player's identity for all subsequent input/fire.
        {:ok, _slot, name} = Room.join(room)

        {:ok, %{name: name}, assign(socket, room: room, name: name)}

      :error ->
        # The join-by-code path (host=false) hit a code with no live room behind
        # it — a typo or a lobby that already shut down. The client surfaces this.
        {:error, %{reason: "not_found"}}
    end
  end

  # A join-by-code (host=false) must land on a room that already exists; the host
  # (host=true) starts it. With no flag at all we stay lenient and find-or-start,
  # which keeps direct URL navigation and the channel tests working.
  defp resolve_room(id, %{"host" => false}) do
    case Rooms.whereis(id) do
      nil -> :error
      pid -> {:ok, pid}
    end
  end

  defp resolve_room(id, _payload), do: Rooms.find_or_start(id, room_opts())

  @impl true
  def terminate(_reason, socket) do
    # Free the slot on disconnect so a departed player stops counting toward the
    # round and isn't re-spawned (otherwise they linger as an inert ghost body).
    with %{room: room, name: name} <- socket.assigns do
      Room.leave(room, name)
    end

    :ok
  end

  @impl true
  def handle_in("input", %{"verb" => verb}, socket) do
    Room.set_verb(socket.assigns.room, socket.assigns.name, to_verb(verb))
    {:reply, :ok, socket}
  end

  def handle_in("fire", %{"x" => x, "y" => y}, socket) do
    event = Room.fire(socket.assigns.room, socket.assigns.name, {x * 1.0, y * 1.0})
    {:reply, {:ok, encode_fire(event)}, socket}
  end

  def handle_in("go", _payload, socket) do
    Room.go(socket.assigns.room)
    {:reply, :ok, socket}
  end

  @impl true
  def handle_info({:lobby, roster}, socket) do
    push(socket, "lobby", roster)
    {:noreply, socket}
  end

  def handle_info(:round_start, socket) do
    push(socket, "round_start", %{})
    {:noreply, socket}
  end

  def handle_info({:snapshot, snapshot}, socket) do
    push(socket, "snapshot", snapshot)
    {:noreply, socket}
  end

  def handle_info({:round_over, outcome, scores}, socket) do
    push(socket, "round_over", Map.put(encode_outcome(outcome), :scores, scores))
    {:noreply, socket}
  end

  # --- Encoding (atoms/tuples → JSON-friendly maps) ---

  defp room_opts do
    Keyword.merge(@default_room_opts, Application.get_env(:death_race, :room, []))
  end

  defp to_verb("walk"), do: :walk
  defp to_verb("run"), do: :run
  defp to_verb(_), do: :stop

  # The client learns only whether its shot was spent — never what it hit.
  defp encode_fire(:fired), do: %{fired: true}
  defp encode_fire(:no_shot), do: %{fired: false}

  defp encode_outcome({:winner, player}), do: %{winner: player}
  defp encode_outcome(:wash), do: %{winner: nil}
end
