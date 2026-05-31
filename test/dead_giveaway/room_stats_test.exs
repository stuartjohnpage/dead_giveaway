defmodule DeadGiveaway.RoomStatsTest do
  @moduledoc "Integration: a Room with a real Accounts stats sink persists wins."
  use DeadGiveaway.DataCase, async: true

  alias DeadGiveaway.{Accounts, Room, World}

  test "a registered player's round win is persisted to their cumulative stats" do
    {:ok, _} = Accounts.register_player("alice")

    {:ok, room} =
      Room.start_link(
        id: "stats-1",
        seed: 1,
        bots: 0,
        finish_x: 2 * World.run_speed(),
        stats: Accounts
      )

    # The room runs in its own process, so let it use the test's sandbox conn.
    Ecto.Adapters.SQL.Sandbox.allow(DeadGiveaway.Repo, self(), room)

    Room.join(room, "alice")
    Room.join(room, "bob")
    Room.go(room)

    # Finish is two run-ticks away, so alice crosses on the second tick and wins.
    Room.set_verb(room, "alice", :run)
    Room.tick(room)
    Room.tick(room)

    assert [%{name: "alice", wins: 1}] = Accounts.leaderboard()
  end
end
