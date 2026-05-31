defmodule DeadGiveaway.AccountsTest do
  use DeadGiveaway.DataCase, async: true

  alias DeadGiveaway.Accounts

  describe "register_player/1" do
    test "creates a player starting at zero wins" do
      assert {:ok, player} = Accounts.register_player("alice")
      assert player.name == "alice"
      assert player.wins == 0
    end

    test "player names are unique" do
      {:ok, _} = Accounts.register_player("alice")
      assert {:error, changeset} = Accounts.register_player("alice")
      refute changeset.valid?
    end
  end

  describe "record_win/1" do
    test "increments a registered player's cumulative wins" do
      {:ok, _} = Accounts.register_player("alice")

      assert {:ok, %{wins: 1}} = Accounts.record_win("alice")
      assert {:ok, %{wins: 2}} = Accounts.record_win("alice")
    end

    test "ignores wins for guests — stats are only tracked for registered players (§8)" do
      assert Accounts.record_win("a-guest") == :ignored
    end
  end

  describe "leaderboard/0" do
    test "ranks players by cumulative wins, descending (wins only score, §8)" do
      {:ok, _} = Accounts.register_player("alice")
      {:ok, _} = Accounts.register_player("bob")
      Accounts.record_win("bob")
      Accounts.record_win("bob")
      Accounts.record_win("alice")

      assert [%{name: "bob", wins: 2}, %{name: "alice", wins: 1}] = Accounts.leaderboard()
    end
  end
end
