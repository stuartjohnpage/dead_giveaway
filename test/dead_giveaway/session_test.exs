defmodule DeadGiveaway.SessionTest do
  use ExUnit.Case, async: true

  alias DeadGiveaway.Session
  alias DeadGiveaway.Session.Player

  describe "joining and naming" do
    test "a blank name takes the lowest free Player N" do
      {0, "Player 1", s} = Session.join(Session.new())
      {1, "Player 2", s} = Session.join(s)
      {2, "Player 3", _s} = Session.join(s)
    end

    test "an explicit name is kept, then disambiguated when already taken" do
      {0, "guest", s} = Session.join(Session.new(), "guest")
      {1, "guest (2)", s} = Session.join(s, "guest")
      {2, "guest (3)", _s} = Session.join(s, "guest")
    end

    test "auto-names reuse the lowest free number rather than climbing" do
      {_, "Player 1", s} = Session.join(Session.new())
      {_, "Player 2", s} = Session.join(s)
      {_, "Player 3", s} = Session.join(s)

      # Free up the number 2; the next auto-named joiner takes it back, not "Player 4".
      s = Session.leave(s, "Player 2")
      {_, "Player 2", _s} = Session.join(s)
    end

    test "slots are monotonic — a freed slot is retired, never reissued" do
      {0, "alice", s} = Session.join(Session.new(), "alice")
      {1, "bob", s} = Session.join(s, "bob")

      # alice's slot 0 is gone; carol must not reuse it (nor land on bob's slot 1).
      s = Session.leave(s, "alice")
      {2, "carol", _s} = Session.join(s, "carol")
    end

    test "join stamps each player with the injected clock" do
      # A deterministic clock proves joined_at is populated from the seam, not wall time.
      {_, _, s} = Session.join(Session.new(clock: fn -> 42 end), "alice")
      assert %Player{name: "alice", slot: 0, joined_at: 42} = Session.player_at(s, 0)
    end
  end

  describe "roster queries" do
    setup do
      {_, _, s} = Session.join(Session.new(), "alice")
      {_, _, s} = Session.join(s, "bob")
      {_, _, s} = Session.join(s, "carol")
      %{session: s}
    end

    test "names are listed in slot order", %{session: s} do
      assert Session.names(s) == ["alice", "bob", "carol"]
    end

    test "players come back slot-ordered (earliest joiner first)", %{session: s} do
      assert Enum.map(Session.players(s), & &1.name) == ["alice", "bob", "carol"]
      assert Enum.map(Session.players(s), & &1.slot) == [0, 1, 2]
    end

    test "count, empty?, member? and player_at reflect the roster", %{session: s} do
      assert Session.count(s) == 3
      refute Session.empty?(s)
      assert Session.member?(s, "bob")
      refute Session.member?(s, "nobody")
      assert %Player{name: "carol"} = Session.player_at(s, 2)
      assert Session.player_at(s, 99) == nil
    end

    test "a fresh session is empty" do
      assert Session.empty?(Session.new())
      assert Session.count(Session.new()) == 0
      assert Session.names(Session.new()) == []
    end
  end

  describe "leaving" do
    test "drops the player's slot and their score tally" do
      {_, _, s} = Session.join(Session.new(), "alice")
      {_, _, s} = Session.join(s, "bob")
      s = Session.award(s, {:winner, "alice"})
      assert Session.score(s, "alice") == 1

      s = Session.leave(s, "alice")
      refute Session.member?(s, "alice")
      assert Session.names(s) == ["bob"]
      # The freed name handed to a new joiner starts from zero, not alice's old win.
      {_, "alice", s} = Session.join(s, "alice")
      assert Session.score(s, "alice") == 0
    end
  end

  describe "scoring" do
    setup do
      {_, _, s} = Session.join(Session.new(), "alice")
      {_, _, s} = Session.join(s, "bob")
      %{session: s}
    end

    test "award({:winner, n}) credits that player one win", %{session: s} do
      s = Session.award(s, {:winner, "alice"})
      assert Session.score(s, "alice") == 1
      assert Session.score(s, "bob") == 0
    end

    test "award(:wash) credits the shared Bot tally", %{session: s} do
      s = Session.award(s, :wash)
      assert Session.score(s, "Bot") == 1
    end

    test "any other outcome is a no-op", %{session: s} do
      assert Session.award(s, :nobody) == s
      # An unrecognised outcome after a real win leaves the tally untouched.
      s = s |> Session.award({:winner, "alice"}) |> Session.award(:abandoned)
      assert Session.score(s, "alice") == 1
    end

    test "the scoreboard lists every current player (0 if winless) plus Bot", %{session: s} do
      s = Session.award(s, {:winner, "alice"})
      board = Session.scoreboard(s)
      assert board == %{"alice" => 1, "bob" => 0, "Bot" => 0}
    end

    test "credit/4 builds a second category that coexists with :wins", %{session: s} do
      s = s |> Session.award({:winner, "alice"}) |> Session.credit("alice", :kills, 3)
      assert Session.score(s, "alice", :wins) == 1
      assert Session.score(s, "alice", :kills) == 3
      # The :wins board is unaffected by the new category.
      assert Session.scoreboard(s, :wins) == %{"alice" => 1, "bob" => 0, "Bot" => 0}
      assert Session.scoreboard(s, :kills) == %{"alice" => 3, "bob" => 0, "Bot" => 0}
    end
  end

  describe "seam defaults reproduce today's behaviour" do
    test "default bot_name is Bot and rides the scoreboard" do
      assert Session.bot_name(Session.new()) == "Bot"
      assert Map.has_key?(Session.scoreboard(Session.new()), "Bot")
    end

    test "a custom bot_name relabels the shared tally" do
      s = Session.new(bot_name: "House")
      s = Session.award(s, :wash)
      assert Session.bot_name(s) == "House"
      assert Session.score(s, "House") == 1
      assert Map.has_key?(Session.scoreboard(s), "House")
    end

    test "a custom namer overrides the naming policy" do
      namer = fn _given, slot, _taken -> "P#{slot}" end
      {0, "P0", s} = Session.join(Session.new(namer: namer))
      {1, "P1", _s} = Session.join(s)
    end

    test "a bare %Session{} literal is fully wired (struct defaults match new/0)" do
      # Bypassing new/0 must not hit a nil namer/clock — join still names and stamps.
      {0, "Player 1", s} = Session.join(%Session{})
      assert Session.bot_name(s) == "Bot"
      assert is_integer(Session.player_at(s, 0).joined_at)
    end
  end
end
