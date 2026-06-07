defmodule DeadGiveawayWeb.LobbiesChannelTest do
  # async: false — these assert on the shared public-lobby directory, so they run serially
  # rather than racing other tests that publish lobbies. Each still filters by its own room
  # code, so a stray entry from elsewhere can't make an assertion pass or fail spuriously.
  use DeadGiveawayWeb.ChannelCase, async: false

  alias DeadGiveaway.{Room, Rooms}
  alias DeadGiveawayWeb.{LobbiesChannel, UserSocket}

  defp join_lobbies do
    {:ok, _reply, socket} =
      socket(UserSocket, nil, %{})
      |> subscribe_and_join(LobbiesChannel, "lobbies", %{})

    socket
  end

  # Drain "lobbies" pushes until one lists `code` (other tests may trigger pushes too), or
  # fail if it never shows. Returns the matching row so callers can assert on its summary.
  defp assert_listed(code, timeout \\ 500) do
    receive do
      %Phoenix.Socket.Message{event: "lobbies", payload: %{lobbies: lobbies}} ->
        case Enum.find(lobbies, &(&1.code == code)) do
          nil -> assert_listed(code, timeout)
          row -> row
        end
    after
      timeout -> flunk("lobby #{code} never appeared in the directory")
    end
  end

  # The mirror of the above: fail if `code` is still listed within the window.
  defp assert_unlisted(code, timeout \\ 500) do
    receive do
      %Phoenix.Socket.Message{event: "lobbies", payload: %{lobbies: lobbies}} ->
        if Enum.any?(lobbies, &(&1.code == code)),
          do: assert_unlisted(code, timeout),
          else: :ok
    after
      timeout -> flunk("lobby #{code} was never removed from the directory")
    end
  end

  test "pushes the current public lobbies on join" do
    {:ok, room} = Rooms.find_or_start("LBA", bots: 0)
    Room.join(room, "alice")
    Room.set_visibility(room, true)

    join_lobbies()
    row = assert_listed("LBA")
    assert row.host == "alice"
    assert row.players == 1
    refute row.in_progress
  end

  test "re-pushes as a room opens, then drops it when it goes private" do
    join_lobbies()
    # The initial snapshot (possibly empty) arrives first.
    assert_push "lobbies", %{lobbies: _}

    {:ok, room} = Rooms.find_or_start("LBB", bots: 0)
    Room.join(room, "alice")
    Room.set_visibility(room, true)
    assert_listed("LBB")

    Room.set_visibility(room, false)
    assert_unlisted("LBB")
  end

  test "a private room never appears in the directory" do
    {:ok, room} = Rooms.find_or_start("LBC", bots: 0)
    Room.join(room, "alice")

    join_lobbies()
    assert_push "lobbies", %{lobbies: lobbies}
    refute Enum.any?(lobbies, &(&1.code == "LBC"))
  end
end
