defmodule DeadGiveawayWeb.RoomChannel do
  @moduledoc """
  Websocket transport for a single Dead Giveaway room (DESIGN §9).

  On join the channel finds-or-starts the room, joins the player into the lobby,
  and subscribes to the room's broadcasts. Inbound messages (`input`, `fire`,
  `aim`, `go`) are routed into the authoritative `Room`; outbound the channel
  forwards the room's `lobby` / `round_start` / `snapshot` / `shot` / `round_over`
  broadcasts — anonymising the snapshot's crosshairs (which the room keys by name)
  into a bare list of points so a reticle never betrays whose it is (DESIGN §5).
  """

  use Phoenix.Channel

  alias DeadGiveaway.{PlayerName, Room, Rooms}

  # Production room shape; overridable via `config :dead_giveaway, :room, ...`
  # (tests use a tiny tick and no bots for determinism). No :bots here — the Room
  # scales the crowd to the player count at each round start (#37).
  @default_room_opts [
    tick_ms: 50,
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
        # Subscribe before joining so we receive our own join's lobby roster. The room
        # broadcasts on its own topic, distinct from this channel's transport topic —
        # see Room.topic/1 — so this is the only delivery of each broadcast.
        Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic(id))

        # The player's chosen name (from the splash) is their identity for all
        # subsequent input/fire; the room uniquifies it and returns the canonical
        # form. A blank name falls back to an auto-assigned "Player N". The room also
        # tells us whether we're the host — assigned server-side to the first joiner,
        # never taken from the client's `host` flag, so a crafted URL can't seize it.
        {:ok, _slot, name, host?} = Room.join(room, normalize_name(payload["name"]))

        # Track host status (only the host may reconfigure or close the lobby) and
        # hand it back in the join reply so the client's lobby controls are right from
        # first paint, not just after the first lobby broadcast. We keep it current
        # from that broadcast too, since the host can change (a hand-off on leave).
        {:ok, %{name: name, host: host?}, assign(socket, room: room, name: name, host: host?)}

      :error ->
        # The join-by-code path (host=false) hit a code with no live room behind
        # it — a typo or a lobby that already shut down. The client surfaces this.
        {:error, %{reason: "not_found"}}
    end
  end

  # The payload `host` flag is only a *create-intent* signal, not a privilege grant
  # (the Room assigns the host server-side): a join-by-code (host=false) must land on a
  # room that already exists, while host=true starts it. With no flag at all we stay
  # lenient and find-or-start, which keeps direct URL navigation and the channel tests
  # working.
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

  # Where this player's crosshair is hovering. High-frequency and fire-and-forget —
  # no reply — since it only feeds the (anonymous) reticle stream, not game logic.
  def handle_in("aim", %{"x" => x, "y" => y}, socket) when is_number(x) and is_number(y) do
    Room.aim(socket.assigns.room, socket.assigns.name, {x * 1.0, y * 1.0})
    {:noreply, socket}
  end

  # Starting a round ("Go" / "Play again") is host-only, like the config knobs below:
  # only the lobby leader launches the game. A guest's Go is acknowledged but ignored,
  # and it's gated server-side, never on the client, so a crafted push can't start it.
  def handle_in("go", _payload, socket) do
    if socket.assigns.host, do: Room.go(socket.assigns.room)
    {:reply, :ok, socket}
  end

  # Lobby config (currently just bullets-per-round). Host-only: a guest's attempt is
  # ignored so they can't change the room out from under the host. The Room clamps
  # the value and broadcasts the new setting to everyone's lobby view.
  def handle_in("set_config", %{"max_ammo" => n}, socket) when is_number(n) do
    if socket.assigns.host, do: Room.set_max_ammo(socket.assigns.room, trunc(n))
    {:reply, :ok, socket}
  end

  # The lives-per-round knob (DESIGN §7), same host-only shape as the bullet count.
  def handle_in("set_config", %{"max_chances" => n}, socket) when is_number(n) do
    if socket.assigns.host, do: Room.set_max_chances(socket.assigns.room, trunc(n))
    {:reply, :ok, socket}
  end

  # The other host-only lobby knob: the room's cosmetic theme. The Room validates the
  # key against the catalogue and broadcasts the change so everyone's art/audio swaps.
  def handle_in("set_config", %{"theme" => theme}, socket) when is_binary(theme) do
    if socket.assigns.host, do: Room.set_theme(socket.assigns.room, theme)
    {:reply, :ok, socket}
  end

  # The round-tempo knob (#17), same host-only shape. The Room validates the value
  # ("slow"/"medium"/"fast") and broadcasts it to every lobby.
  def handle_in("set_config", %{"pace" => pace}, socket) when is_binary(pace) do
    if socket.assigns.host, do: Room.set_pace(socket.assigns.room, pace)
    {:reply, :ok, socket}
  end

  # The game-mode knob (#53), same host-only shape. The Room validates the value
  # ("classic"/"red_light") and broadcasts it to every lobby.
  def handle_in("set_config", %{"mode" => mode}, socket) when is_binary(mode) do
    if socket.assigns.host, do: Room.set_mode(socket.assigns.room, mode)
    {:reply, :ok, socket}
  end

  # Public/private visibility (issue #43), same host-only shape. The Room lists or unlists
  # the lobby in the directory and broadcasts the new value so every lobby view reflects it.
  def handle_in("set_config", %{"public" => public}, socket) when is_boolean(public) do
    if socket.assigns.host, do: Room.set_visibility(socket.assigns.room, public)
    {:reply, :ok, socket}
  end

  # Catch-all for set_config: an unknown key or a value that fails a clause's guard (e.g. a
  # crafted `{"public": "yes"}`) is ignored rather than left to raise FunctionClauseError and
  # crash the channel — which would boot the player from the lobby. The Room is the authority;
  # a malformed knob simply does nothing.
  def handle_in("set_config", _payload, socket), do: {:reply, :ok, socket}

  # Change your display name while in the lobby (#63). The raw value passes the same
  # trim/profanity chokepoint as a join, and the Room applies the same collision
  # disambiguation — then broadcasts the refreshed roster to everyone. The lobby-only
  # gate lives in the Room (mid-round names are identity). A blank or failed rename
  # keeps the current name; either way the reply carries the name now in force so the
  # client can adopt the canonical form.
  def handle_in("rename", %{"name" => raw}, socket) do
    with new when not is_nil(new) <- normalize_name(raw),
         {:ok, name} <- Room.rename(socket.assigns.room, socket.assigns.name, new) do
      {:reply, {:ok, %{name: name}}, assign(socket, name: name)}
    else
      _ -> {:reply, {:ok, %{name: socket.assigns.name}}, socket}
    end
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
    # The Room is the authority on who hosts; refresh our flag from each roster (it
    # shifts if the host leaves and the room hands off) before forwarding the roster,
    # whose `host` name lets the client tell whether it's the host.
    socket = assign(socket, host: roster.host == socket.assigns.name)
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
    push(socket, "snapshot", anonymize_crosshairs(snapshot, socket.assigns.name))
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

  # A private "you're out" — the room tells the owner whose body just dropped (#11).
  # Every channel sees this broadcast, but only the named owner forwards it to its
  # browser, so a body dropping still reveals nothing to peers (DESIGN §5). The client
  # drops its reticle and stops firing on this; peers' view is unchanged.
  def handle_info({:player_out, name}, socket) do
    if name == socket.assigns.name, do: push(socket, "out", %{})
    {:noreply, socket}
  end

  # Private lives-remaining update for the HUD (DESIGN §7). Like "out", every channel
  # sees the broadcast but only the named owner forwards it — a takeover (which spends a
  # life but keeps you alive) never tips peers off (DESIGN §5).
  def handle_info({:chances, name, n}, socket) do
    if name == socket.assigns.name, do: push(socket, "chances", %{chances: n})
    {:noreply, socket}
  end

  # Private "this is your body" (#41): the room tells each owner the entity id they
  # drive — at round start, and again on a bot takeover (§7) — so their client can
  # predict its own motion. Like "out"/"chances", every channel sees the broadcast but
  # only the named owner forwards it: peers learn nothing, and only your OWN id ever
  # reaches a browser — the full human/bot mapping stays server-side (DESIGN §2, §9).
  def handle_info({:you_are, name, id}, socket) do
    if name == socket.assigns.name, do: push(socket, "you", %{id: id})
    {:noreply, socket}
  end

  # --- Encoding (atoms/tuples → JSON-friendly maps) ---

  defp room_opts do
    Keyword.merge(@default_room_opts, Application.get_env(:dead_giveaway, :room, []))
  end

  # A chosen name from the client: trimmed, length-capped, then profanity-redacted (#13);
  # blank → nil (the room then auto-names the player "Player N"). The rule itself lives
  # in PlayerName.normalize/1 — the single chokepoint both join and rename flow through —
  # so a crafted payload can't reach a path the filter doesn't cover.
  defp normalize_name(name), do: PlayerName.normalize(name)

  defp to_verb("walk"), do: :walk
  defp to_verb("run"), do: :run
  defp to_verb(_), do: :stop

  # The client learns only whether its shot was spent — never what it hit.
  defp encode_fire(:fired), do: %{fired: true}
  defp encode_fire(:no_shot), do: %{fired: false}

  defp encode_outcome({:winner, player}), do: %{winner: player}
  # A bot crossed first — the shared Bot opponent takes the round (no more "wash").
  defp encode_outcome(:wash), do: %{winner: Room.bot_name()}
  # Every human is out (#55) — game over with nobody, not even the Bot, taking the round.
  defp encode_outcome(:wipe), do: %{winner: nil}

  # The room keys crosshairs by name (it's the trusted authority); a browser must
  # never see that. Strip the recipient's own reticle — their client draws it live
  # from the mouse — then drop the names entirely, leaving a bare list of points.
  # Sorted by name so a given peer keeps a stable slot across snapshots (smooth
  # client-side interpolation) without that order ever revealing who they are.
  defp anonymize_crosshairs(%{crosshairs: crosshairs} = snapshot, me) do
    points =
      crosshairs
      |> Enum.reject(fn {name, _point} -> name == me end)
      |> Enum.sort_by(fn {name, _point} -> name end)
      |> Enum.map(fn {_name, point} -> point end)

    %{snapshot | crosshairs: points}
  end

  defp anonymize_crosshairs(snapshot, _me), do: snapshot
end
