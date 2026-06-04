defmodule DeadGiveawayWeb.RoomChannelTest do
  use DeadGiveawayWeb.ChannelCase, async: true

  alias DeadGiveaway.{Rooms, Session}
  alias DeadGiveawayWeb.{RoomChannel, UserSocket}

  defp join_room(id, payload \\ %{}) do
    {:ok, reply, socket} =
      socket(UserSocket, nil, %{})
      |> subscribe_and_join(RoomChannel, "room:" <> id, payload)

    {reply, socket}
  end

  # Registry deregistration is asynchronous w.r.t. a process's death, so a lookup can
  # briefly still see a just-stopped room even after its :DOWN arrives. Retry the
  # predicate over a short bounded window rather than checking exactly once.
  defp eventually(fun, retries \\ 50) do
    cond do
      fun.() -> true
      retries > 0 -> Process.sleep(2) || eventually(fun, retries - 1)
      true -> false
    end
  end

  test "a player can join a room channel" do
    assert {_reply, %Phoenix.Socket{}} = join_room("chan-a")
  end

  test "the host (host=true) starts the room on join" do
    assert {_reply, %Phoenix.Socket{}} = join_room("chan-host", %{"host" => true})
    assert Rooms.whereis("chan-host")
  end

  test "joining by code (host=false) a lobby that isn't live is rejected" do
    error =
      socket(UserSocket, nil, %{})
      |> subscribe_and_join(RoomChannel, "room:chan-missing", %{"host" => false})

    assert {:error, %{reason: "not_found"}} = error
    refute Rooms.whereis("chan-missing")
  end

  test "joining by code (host=false) succeeds once the lobby is live" do
    join_room("chan-live", %{"host" => true})
    assert {_reply, %Phoenix.Socket{}} = join_room("chan-live", %{"host" => false})
  end

  test "joiners get distinct auto-assigned identities" do
    {reply1, _s1} = join_room("chan-id")
    {reply2, _s2} = join_room("chan-id")

    assert reply1.name == "Player 1"
    assert reply2.name == "Player 2"
  end

  test "a profane chosen name is redacted server-side before it's assigned (#13)" do
    {reply, _s} = join_room("chan-clean", %{"name" => "ShitLord"})
    assert reply.name == "****Lord"
  end

  test "clients receive the lobby roster" do
    join_room("chan-lobby")
    join_room("chan-lobby")

    assert_push "lobby", %{players: players}, 500
    assert "Player 1" in players
  end

  test "world snapshots are pushed to clients once a round is running" do
    {_reply, host} = join_room("chan-b", %{"host" => true})
    join_room("chan-b")
    push(host, "go", %{})

    assert_push "snapshot", %{entities: entities}, 500
    assert is_list(entities)
  end

  test "clients are told when a round starts" do
    {_reply, host} = join_room("chan-start", %{"host" => true})
    join_room("chan-start")
    push(host, "go", %{})

    assert_push "round_start", %{}, 500
  end

  test "a host's go is accepted and acknowledged" do
    {_reply, host} = join_room("chan-go", %{"host" => true})

    ref = push(host, "go", %{})
    assert_reply ref, :ok
  end

  test "a guest's go is ignored — only the host starts the round" do
    join_room("chan-go-guest", %{"host" => true})
    {_reply, guest} = join_room("chan-go-guest", %{"host" => false})

    # The push is still acknowledged, but the round never starts on a guest's say-so.
    ref = push(guest, "go", %{})
    assert_reply ref, :ok
    refute_push "round_start", %{}, 200
  end

  test "a fire message spends the shot without revealing what it hit" do
    {_reply, host} = join_room("chan-c", %{"host" => true})
    {_reply, socket} = join_room("chan-c")

    go = push(host, "go", %{})
    assert_reply go, :ok

    ref = push(socket, "fire", %{"x" => 0.0, "y" => 0.0})
    # The reply confirms the shot was spent — never whether it hit human or bot.
    assert_reply ref, :ok, reply
    assert reply == %{fired: true}

    # The shot is broadcast to the room, so every connected client — including
    # the shooter — gets a "shot" push to play the SFX (it carries nothing else).
    assert_push "shot", %{}
  end

  test "a player whose body is dropped is privately told they're out (#11)" do
    {_reply, socket} = join_room("chan-out-self", %{"host" => true})

    go = push(socket, "go", %{})
    assert_reply go, :ok
    # Wait until the round is actually running before firing.
    assert_push "snapshot", %{entities: [_ | _]}, 500

    # Solo player is the only body, so firing at the origin drops their own — they're
    # out, and the room tells them so privately.
    ref = push(socket, "fire", %{"x" => 0.0, "y" => 0.0})
    assert_reply ref, :ok, %{fired: true}
    assert_push "out", %{}, 500
  end

  test "the 'out' signal never reaches a player who wasn't the one dropped (#11)" do
    # One channel (the host) plus a second, channel-less player we drop directly via
    # the Room — so any "out" reaching this channel would be a leak.
    {_reply, socket} = join_room("chan-out-peer", %{"host" => true})
    room = Rooms.whereis("chan-out-peer")
    DeadGiveaway.Room.join(room, "victim")

    go = push(socket, "go", %{})
    assert_reply go, :ok
    assert_push "snapshot", %{entities: [_ | _]}, 500

    # Drop "victim" by aiming exactly at their row; the host channel must stay silent.
    victim_row = :sys.get_state(room).world.slot_of["victim"]
    DeadGiveaway.Room.fire(room, "victim", {0.0, victim_row * DeadGiveaway.World.row_spacing()})
    refute_push "out", %{}, 200
  end

  test "a peer's crosshair reaches you as an anonymous point, and never your own" do
    {_r1, host} = join_room("chan-aim", %{"host" => true})
    {_r2, guest} = join_room("chan-aim", %{"host" => false})

    go = push(host, "go", %{})
    assert_reply go, :ok

    # Both players aim somewhere; the guest's view should carry the host's reticle
    # as a bare point (no name) and omit the guest's own (drawn locally from the mouse).
    push(host, "aim", %{"x" => 7.0, "y" => 3.0})
    push(guest, "aim", %{"x" => 1.0, "y" => 1.0})

    # Snapshots stream at the tick rate; wait for one carrying the host's point.
    # Positions ride the wire quantized to whole world units (#39), so 7.0/3.0 → 7/3.
    assert_push "snapshot", %{crosshairs: [%{x: 7, y: 3}]}, 500
  end

  test "the host can set the bullet count and it reaches every client's lobby" do
    {_reply, socket} = join_room("chan-ammo", %{"host" => true})

    ref = push(socket, "set_config", %{"max_ammo" => 4})
    assert_reply ref, :ok

    assert_push "lobby", %{max_ammo: 4}, 500
  end

  test "the host can set the life count and it reaches every client's lobby" do
    {_reply, socket} = join_room("chan-lives", %{"host" => true})

    ref = push(socket, "set_config", %{"max_chances" => 3})
    assert_reply ref, :ok

    assert_push "lobby", %{max_chances: 3}, 500
  end

  test "the host can set the pace and it reaches every client's lobby (#17)" do
    {_reply, socket} = join_room("chan-pace", %{"host" => true})

    ref = push(socket, "set_config", %{"pace" => "slow"})
    assert_reply ref, :ok

    assert_push "lobby", %{pace: :slow}, 500
  end

  test "a guest cannot change the pace (#17)" do
    join_room("chan-pace-guest", %{"host" => true})
    {_reply, guest} = join_room("chan-pace-guest", %{"host" => false})

    ref = push(guest, "set_config", %{"pace" => "slow"})
    assert_reply ref, :ok
    refute_push "lobby", %{pace: :slow}, 200
  end

  test "a guest cannot change the life count" do
    join_room("chan-lives-guest", %{"host" => true})
    {_reply, guest} = join_room("chan-lives-guest", %{"host" => false})

    ref = push(guest, "set_config", %{"max_chances" => 3})
    assert_reply ref, :ok
    refute_push "lobby", %{max_chances: 3}, 200
  end

  test "a guest cannot change the bullet count" do
    join_room("chan-ammo-guest", %{"host" => true})
    {_reply, guest} = join_room("chan-ammo-guest", %{"host" => false})

    ref = push(guest, "set_config", %{"max_ammo" => 4})
    assert_reply ref, :ok
    # The room ignores a non-host's config push, so no lobby ever carries the change.
    refute_push "lobby", %{max_ammo: 4}, 200
  end

  test "a second joiner claiming host=true in the payload cannot seize the lobby" do
    # The real host opens the room...
    {_r, host} = join_room("chan-steal", %{"host" => true})
    # ...then an interloper joins forging host=true (as a crafted websocket payload would).
    {_r2, thief} = join_room("chan-steal", %{"host" => true})
    room = Rooms.whereis("chan-steal")

    # The room assigns host server-side to the first player, so the forged flag is
    # ignored: the thief's config push is dropped, and their "leave" only frees their
    # own slot rather than closing the room out from under the real host.
    ref = push(thief, "set_config", %{"max_ammo" => 4})
    assert_reply ref, :ok
    refute_push "lobby", %{max_ammo: 4}, 200

    ref = push(thief, "leave", %{})
    assert_reply ref, :ok
    assert Rooms.whereis("chan-steal")
    assert "Player 1" in Session.names(:sys.get_state(room).session)

    # The genuine host still holds the privilege.
    ref = push(host, "set_config", %{"max_ammo" => 4})
    assert_reply ref, :ok
    assert_push "lobby", %{max_ammo: 4}, 500
  end

  test "host hands off to the remaining player when the original host disconnects" do
    {_r, host} = join_room("chan-handoff", %{"host" => true})
    {_r2, guest} = join_room("chan-handoff", %{"host" => false})

    # The original host's channel closes (a disconnect, not the "Close lobby" button),
    # so terminate/2 frees their slot and the room hands host off to the guest.
    chan = host.channel_pid
    ref_down = Process.monitor(chan)
    Process.unlink(chan)
    leave(host)
    assert_receive {:DOWN, ^ref_down, :process, ^chan, _}

    # The promoted guest can now reconfigure the lobby — proof the privilege moved.
    ref = push(guest, "set_config", %{"max_ammo" => 5})
    assert_reply ref, :ok
    assert_push "lobby", %{max_ammo: 5}, 500
  end

  test "the host can set the theme and it reaches every client's lobby" do
    {_reply, socket} = join_room("chan-theme", %{"host" => true})

    ref = push(socket, "set_config", %{"theme" => "western"})
    assert_reply ref, :ok

    assert_push "lobby", %{theme: "western"}, 500
  end

  test "a guest cannot change the theme" do
    join_room("chan-theme-guest", %{"host" => true})
    {_reply, guest} = join_room("chan-theme-guest", %{"host" => false})

    ref = push(guest, "set_config", %{"theme" => "western"})
    assert_reply ref, :ok
    # As with the bullet count, a non-host's push is ignored — no lobby carries it.
    refute_push "lobby", %{theme: "western"}, 200
  end

  test "an input message is accepted and acknowledged" do
    join_room("chan-d")
    {_reply, socket} = join_room("chan-d")

    ref = push(socket, "input", %{"verb" => "run"})
    assert_reply ref, :ok
  end

  test "a guest's leave message frees their slot without closing the room" do
    join_room("chan-guest-leave", %{"host" => true})
    {_reply, socket} = join_room("chan-guest-leave", %{"host" => false})

    room = Rooms.whereis("chan-guest-leave")
    assert Session.count(:sys.get_state(room).session) == 2

    ref = push(socket, "leave", %{})
    assert_reply ref, :ok

    # The room is still live for the remaining (host) player.
    assert Rooms.whereis("chan-guest-leave")
    assert Session.count(:sys.get_state(room).session) == 1
  end

  test "the host's leave message closes the lobby for everyone" do
    {_reply, host} = join_room("chan-host-close", %{"host" => true})
    join_room("chan-host-close", %{"host" => false})

    room = Rooms.whereis("chan-host-close")
    ref_down = Process.monitor(room)

    ref = push(host, "leave", %{})
    assert_reply ref, :ok

    # Every client (the closing host included) is told the lobby is gone...
    assert_push "closed", %{}
    # ...and the room process is actually torn down, freeing its code (once the
    # Registry has processed its own :DOWN and dropped the entry).
    assert_receive {:DOWN, ^ref_down, :process, ^room, _}
    assert eventually(fn -> is_nil(Rooms.whereis("chan-host-close")) end)
  end

  test "leaving the channel frees the player's slot in the room" do
    join_room("chan-leave")
    {_reply, socket} = join_room("chan-leave")

    room = Rooms.whereis("chan-leave")
    assert Session.count(:sys.get_state(room).session) == 2

    # Closing the channel runs terminate/2 (a synchronous Room.leave), so once
    # the channel process is down the room has already dropped the player.
    chan = socket.channel_pid
    ref_down = Process.monitor(chan)
    Process.unlink(chan)
    ref = leave(socket)
    assert_reply ref, :ok
    assert_receive {:DOWN, ^ref_down, :process, ^chan, _}

    names = Session.names(:sys.get_state(room).session)
    assert length(names) == 1
    assert "Player 2" not in names
    assert "Player 1" in names
  end
end
