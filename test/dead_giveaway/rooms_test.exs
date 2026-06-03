defmodule DeadGiveaway.RoomsTest do
  use ExUnit.Case, async: true

  alias DeadGiveaway.{Room, Rooms}

  test "find_or_start starts a room addressable by its id" do
    {:ok, pid} = Rooms.find_or_start("game-a")

    assert Process.alive?(pid)
    assert Rooms.whereis("game-a") == pid
  end

  test "find_or_start is idempotent — the same id returns the same room" do
    {:ok, pid1} = Rooms.find_or_start("game-b")
    {:ok, pid2} = Rooms.find_or_start("game-b")

    assert pid1 == pid2
  end

  test "a room found by id can be joined" do
    {:ok, _pid} = Rooms.find_or_start("game-c")

    assert {:ok, 0, "alice", _host?} = Room.join(Rooms.whereis("game-c"), "alice")
  end

  test "rooms are supervised — a crashed room is restarted under the same id" do
    {:ok, pid} = Rooms.find_or_start("game-d")
    ref = Process.monitor(pid)

    Process.exit(pid, :kill)
    assert_receive {:DOWN, ^ref, :process, ^pid, _}, 500

    # The supervisor restarts it and it re-registers under the same id. The
    # Registry clears the dead pid asynchronously, so wait for a *fresh* one.
    new_pid =
      eventually(fn ->
        case Rooms.whereis("game-d") do
          p when is_pid(p) and p != pid -> p
          _ -> nil
        end
      end)

    assert is_pid(new_pid)
    assert Process.alive?(new_pid)
  end

  defp eventually(fun, tries \\ 50) do
    case fun.() do
      nil when tries > 0 -> Process.sleep(10) && eventually(fun, tries - 1)
      result -> result
    end
  end
end
