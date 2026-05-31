defmodule DeadGiveawayWeb.RoomChannelTest do
  use DeadGiveawayWeb.ChannelCase, async: true

  alias DeadGiveaway.Rooms
  alias DeadGiveawayWeb.{RoomChannel, UserSocket}

  defp join_room(id, payload \\ %{}) do
    {:ok, reply, socket} =
      socket(UserSocket, nil, %{})
      |> subscribe_and_join(RoomChannel, "room:" <> id, payload)

    {reply, socket}
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

  test "clients receive the lobby roster" do
    join_room("chan-lobby")
    join_room("chan-lobby")

    assert_push "lobby", %{players: players}, 500
    assert "Player 1" in players
  end

  test "world snapshots are pushed to clients once a round is running" do
    join_room("chan-b")
    {_reply, socket} = join_room("chan-b")
    push(socket, "go", %{})

    assert_push "snapshot", %{entities: entities}, 500
    assert is_list(entities)
  end

  test "clients are told when a round starts" do
    join_room("chan-start")
    {_reply, socket} = join_room("chan-start")
    push(socket, "go", %{})

    assert_push "round_start", %{}, 500
  end

  test "a go message is accepted and acknowledged" do
    {_reply, socket} = join_room("chan-go")

    ref = push(socket, "go", %{})
    assert_reply ref, :ok
  end

  test "a fire message spends the shot without revealing what it hit" do
    join_room("chan-c")
    {_reply, socket} = join_room("chan-c")

    go = push(socket, "go", %{})
    assert_reply go, :ok

    ref = push(socket, "fire", %{"x" => 0.0, "y" => 0.0})
    # The reply confirms the shot was spent — never whether it hit human or bot.
    assert_reply ref, :ok, reply
    assert reply == %{fired: true}
  end

  test "an input message is accepted and acknowledged" do
    join_room("chan-d")
    {_reply, socket} = join_room("chan-d")

    ref = push(socket, "input", %{"verb" => "run"})
    assert_reply ref, :ok
  end

  test "leaving the channel frees the player's slot in the room" do
    join_room("chan-leave")
    {_reply, socket} = join_room("chan-leave")

    room = Rooms.whereis("chan-leave")
    assert map_size(:sys.get_state(room).players) == 2

    # Closing the channel runs terminate/2 (a synchronous Room.leave), so once
    # the channel process is down the room has already dropped the player.
    chan = socket.channel_pid
    ref_down = Process.monitor(chan)
    Process.unlink(chan)
    ref = leave(socket)
    assert_reply ref, :ok
    assert_receive {:DOWN, ^ref_down, :process, ^chan, _}

    players = :sys.get_state(room).players
    assert map_size(players) == 1
    assert "Player 2" not in Map.values(players)
    assert "Player 1" in Map.values(players)
  end
end
