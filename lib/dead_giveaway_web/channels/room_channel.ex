defmodule DeadGiveawayWeb.RoomChannel do
  @moduledoc """
  Websocket transport for a single Dead Giveaway room (DESIGN §9).

  On join the channel finds-or-starts the room, joins the player into the lobby,
  and subscribes to the room's broadcasts. Inbound messages (`input`, `fire`,
  `go`) are routed into the authoritative `Room`; outbound the channel forwards
  the room's `lobby` / `round_start` / `snapshot` / `shot` / `round_over`
  broadcasts.
  """

  use Phoenix.Channel

  alias DeadGiveaway.{Room, Rooms}

  # Production room shape; overridable via `config :dead_giveaway, :room, ...`
  # (tests use a tiny tick and no bots for determinism).
  @default_room_opts [
    tick_ms: 50,
    bots: 24,
    finish_x: 500.0,
    stats: DeadGiveaway.Accounts,
    # Abandoned lobbies (and their codes) shut down a minute after the last
    # player leaves; a reconnect within the window keeps the room alive.
    empty_after_ms: 60_000
  ]

  @impl true
  def join("room:" <> id, payload, socket) do
    case resolve_room(id, payload) do
      {:ok, room} ->
        # Subscribe before joining so we receive our own join's lobby roster.
        Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic(id))

        # The player's chosen name (from the splash) is their identity for all
        # subsequent input/fire; the room uniquifies it and returns the canonical
        # form. A blank name falls back to an auto-assigned "Player N".
        {:ok, _slot, name} = Room.join(room, normalize_name(payload["name"]))

        # Remember whether this client is the host (host=true) — only the host can
        # close the lobby out from under everyone when they back out.
        {:ok, %{name: name},
         assign(socket, room: room, name: name, host: payload["host"] == true)}

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
    # A host who just closed the lobby leaves a stopped room behind, so the call
    # can hit a dead pid — swallow that exit, the room is already gone.
    with %{room: room, name: name} <- socket.assigns do
      try do
        Room.leave(room, name)
      catch
        :exit, _ -> :ok
      end
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

  # Lobby config (currently just bullets-per-round). Host-only: a guest's attempt is
  # ignored so they can't change the room out from under the host. The Room clamps
  # the value and broadcasts the new setting to everyone's lobby view.
  def handle_in("set_config", %{"max_ammo" => n}, socket) when is_number(n) do
    if socket.assigns.host, do: Room.set_max_ammo(socket.assigns.room, trunc(n))
    {:reply, :ok, socket}
  end

  # Backing out of the lobby. The host tears the whole room down (everyone is sent
  # `closed`); a guest just frees their own slot and heads home on their own.
  def handle_in("leave", _payload, socket) do
    %{room: room, name: name, host: host} = socket.assigns
    if host, do: Room.close(room), else: Room.leave(room, name)
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

  # The host closed the lobby — tell this client so it can drop back to home.
  def handle_info(:closed, socket) do
    push(socket, "closed", %{})
    {:noreply, socket}
  end

  def handle_info({:snapshot, snapshot}, socket) do
    push(socket, "snapshot", snapshot)
    {:noreply, socket}
  end

  # An anonymous gunshot — someone in the room fired. Every client plays the
  # SFX; the message deliberately carries no shooter or outcome (DESIGN §5).
  def handle_info(:shot, socket) do
    push(socket, "shot", %{})
    {:noreply, socket}
  end

  def handle_info({:round_over, outcome, scores}, socket) do
    push(socket, "round_over", Map.put(encode_outcome(outcome), :scores, scores))
    {:noreply, socket}
  end

  # --- Encoding (atoms/tuples → JSON-friendly maps) ---

  defp room_opts do
    Keyword.merge(@default_room_opts, Application.get_env(:dead_giveaway, :room, []))
  end

  # A chosen name from the client: trimmed and length-capped, blank → nil (the
  # room then auto-names the player "Player N").
  defp normalize_name(name) do
    case name |> to_string() |> String.trim() |> String.slice(0, 16) do
      "" -> nil
      n -> n
    end
  end

  defp to_verb("walk"), do: :walk
  defp to_verb("run"), do: :run
  defp to_verb(_), do: :stop

  # The client learns only whether its shot was spent — never what it hit.
  defp encode_fire(:fired), do: %{fired: true}
  defp encode_fire(:no_shot), do: %{fired: false}

  defp encode_outcome({:winner, player}), do: %{winner: player}
  # A bot crossed first — the shared Bot opponent takes the round (no more "wash").
  defp encode_outcome(:wash), do: %{winner: Room.bot_name()}
end
