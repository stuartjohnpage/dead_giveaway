defmodule DeadGiveaway.RoomTest do
  use ExUnit.Case, async: true

  alias DeadGiveaway.Room
  alias DeadGiveaway.World

  describe "starting a room" do
    test "starts a supervised process that stays alive" do
      {:ok, room} = Room.start_link(id: "r1")
      assert Process.alive?(room)
    end
  end

  describe "joining" do
    test "assigns the first player slot 0" do
      {:ok, room} = Room.start_link(id: "r1")
      assert {:ok, 0, "alice"} = Room.join(room, "alice")
    end

    test "assigns sequential slots to subsequent players" do
      {:ok, room} = Room.start_link(id: "r1")
      assert {:ok, 0, "alice"} = Room.join(room, "alice")
      assert {:ok, 1, "bob"} = Room.join(room, "bob")
      assert {:ok, 2, "carol"} = Room.join(room, "carol")
    end

    test "auto-names players Player N when no name is given" do
      {:ok, room} = Room.start_link(id: "r1")
      assert {:ok, 0, "Player 1"} = Room.join(room)
      assert {:ok, 1, "Player 2"} = Room.join(room)
    end

    test "disambiguates an explicit name already taken so two players never collapse" do
      {:ok, room} = Room.start_link(id: "r1")
      assert {:ok, 0, "guest"} = Room.join(room, "guest")
      assert {:ok, 1, "guest (2)"} = Room.join(room, "guest")
      assert {:ok, 2, "guest (3)"} = Room.join(room, "guest")
    end
  end

  describe "leaving" do
    test "frees the slot and stops the player counting toward the round" do
      {:ok, room} = Room.start_link(id: "leave-1")
      Room.join(room, "alice")
      Room.join(room, "bob")
      Room.go(room)
      assert Room.status(room) == :running

      :ok = Room.leave(room, "bob")
      # bob no longer occupies a slot, so he won't pad the headcount or be
      # re-spawned as an inert ghost on the next round.
      players = :sys.get_state(room).players
      assert map_size(players) == 1
      assert Map.values(players) == ["alice"]
    end

    test "a freed slot is never reassigned to a still-present player" do
      {:ok, room} = Room.start_link(id: "leave-2")
      {:ok, 0, _} = Room.join(room, "alice")
      {:ok, 1, _} = Room.join(room, "bob")
      :ok = Room.leave(room, "alice")
      # Next joiner must not reuse slot 0 (alice's old slot is gone) AND must not
      # land on bob's slot 1.
      assert {:ok, 2, "carol"} = Room.join(room, "carol")
    end
  end

  describe "empty-lobby expiry" do
    test "an empty room shuts itself down after the grace period" do
      {:ok, room} = Room.start_link(id: "expire-1", empty_after_ms: 10)
      Room.join(room, "alice")
      ref = Process.monitor(room)

      :ok = Room.leave(room, "alice")

      # The last player left, so the room expires on its own (a normal exit).
      assert_receive {:DOWN, ^ref, :process, ^room, :normal}, 500
    end

    test "a player rejoining before the grace period cancels the shutdown" do
      {:ok, room} = Room.start_link(id: "expire-2", empty_after_ms: 50)
      Room.join(room, "alice")
      :ok = Room.leave(room, "alice")

      # Rejoin well within the window — the pending shutdown must be cancelled.
      {:ok, _, "bob"} = Room.join(room, "bob")
      ref = Process.monitor(room)
      refute_receive {:DOWN, ^ref, :process, ^room, _}, 120
    end

    test "a room with expiry disabled (the default) never auto-expires when emptied" do
      {:ok, room} = Room.start_link(id: "expire-3")
      Room.join(room, "alice")
      ref = Process.monitor(room)

      :ok = Room.leave(room, "alice")

      refute_receive {:DOWN, ^ref, :process, ^room, _}, 50
    end
  end

  describe "a mid-round joiner" do
    test "spectates without crashing the room when they send input" do
      {:ok, room} = Room.start_link(id: "midjoin-1", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.join(room, "bob")
      Room.go(room)
      assert Room.status(room) == :running

      # carol joins after the round started — she has no body this round (§8).
      {:ok, _, "carol"} = Room.join(room, "carol")
      ref = Process.monitor(room)

      # Her input must be ignored, not crash the room (and everyone in it).
      assert :ok = Room.set_verb(room, "carol", :walk)
      refute_receive {:DOWN, ^ref, :process, ^room, _}, 100
      assert Process.alive?(room)
    end
  end

  describe "starting a round" do
    test "joining the lobby does not start a round on its own" do
      {:ok, room} = Room.start_link(id: "round-1")
      Room.join(room, "alice")
      Room.join(room, "bob")
      assert Room.status(room) == :waiting
    end

    test "Go starts a round — a lone player may play against the bots" do
      {:ok, room} = Room.start_link(id: "round-2")
      Room.join(room, "alice")
      assert Room.status(room) == :waiting

      Room.go(room)
      assert Room.status(room) == :running
    end

    test "Go with nobody in the lobby does nothing" do
      {:ok, room} = Room.start_link(id: "round-3")
      Room.go(room)
      assert Room.status(room) == :waiting
    end
  end

  describe "ticking a live round" do
    setup do
      {:ok, room} = Room.start_link(id: "tick-1", seed: 1, bots: 2)
      Room.join(room, "alice")
      Room.join(room, "bob")
      Room.go(room)
      %{room: room}
    end

    test "broadcasts a real world snapshot of every character", %{room: room} do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("tick-1"))

      {:ok, snap} = Room.tick(room)

      # 2 humans + 2 bots, all present in the public snapshot.
      assert length(snap.entities) == 4
      assert_receive {:snapshot, %{entities: _}}, 500
    end
  end

  describe "routing player input into the world" do
    test "a player's verb drives their character down the track" do
      {:ok, room} = Room.start_link(id: "input-1", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.join(room, "bob")
      Room.go(room)

      Room.set_verb(room, "alice", :run)

      snap =
        Enum.reduce(1..3, nil, fn _, _ ->
          {:ok, s} = Room.tick(room)
          s
        end)

      # alice ran for 3 ticks; bob stayed put. Exactly one mover, at run pace.
      assert Enum.any?(snap.entities, &(&1.x >= 3 * World.run_speed()))
    end
  end

  describe "finishing a round" do
    test "a human winner is announced and awarded a cumulative win" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("win-1"))

      {:ok, room} =
        Room.start_link(id: "win-1", seed: 1, bots: 0, finish_x: 2 * World.run_speed())

      Room.join(room, "alice")
      Room.join(room, "bob")
      Room.go(room)

      # Finish is two run-ticks away, so alice crosses on the second tick.
      Room.set_verb(room, "alice", :run)
      Room.tick(room)
      Room.tick(room)

      assert_receive {:round_over, {:winner, "alice"}, scores}, 500
      assert scores["alice"] == 1
      # The scoreboard lists every player (0 if they've not finished first) plus
      # the shared Bot tally — it reads like the lobby roster, not just winners.
      assert scores["bob"] == 0
      assert scores["Bot"] == 0
      assert Room.score(room, "alice") == 1
      assert Room.score(room, "bob") == 0
    end

    test "a bot crossing first credits the shared Bot tally (no wash)" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("botwin-1"))

      {:ok, room} =
        Room.start_link(id: "botwin-1", seed: 1, bots: 1, finish_x: 3 * World.walk_speed())

      Room.join(room, "alice")
      Room.go(room)

      # alice never moves, so the only thing that can cross is the lone bot.
      Enum.each(1..200, fn _ -> Room.tick(room) end)

      assert_receive {:round_over, :wash, scores}, 500
      assert scores["Bot"] == 1
      assert scores["alice"] == 0
      assert Room.score(room, "Bot") == 1
    end
  end

  describe "firing" do
    test "a spent bullet broadcasts an anonymous shot to the room" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("shot-1"))

      {:ok, room} = Room.start_link(id: "shot-1", seed: 1, bots: 2)
      Room.join(room, "alice")
      Room.go(room)

      assert Room.fire(room, "alice", {0.0, 0.0}) == :fired
      # Everyone in the room hears the crack — but it carries no shooter,
      # position, or outcome (DESIGN §5).
      assert_receive :shot, 500
    end

    test "an empty trigger-pull (bullet already spent) stays silent" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("shot-2"))

      {:ok, room} = Room.start_link(id: "shot-2", seed: 1, bots: 2)
      Room.join(room, "alice")
      Room.go(room)

      assert Room.fire(room, "alice", {0.0, 0.0}) == :fired
      assert_receive :shot, 500

      # alice is out of bullets — a second pull does nothing and makes no sound.
      assert Room.fire(room, "alice", {0.0, 0.0}) == :no_shot
      refute_receive :shot, 200
    end

    test "the host's bullet count reaches every lobby view" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("ammo-1"))
      {:ok, room} = Room.start_link(id: "ammo-1", seed: 1, bots: 0)
      # A fresh lobby defaults to one bullet (DESIGN §5).
      Room.join(room, "alice")
      assert_receive {:lobby, %{max_ammo: 1}}

      # The host raising it re-broadcasts the roster carrying the new count.
      Room.set_max_ammo(room, 3)
      assert_receive {:lobby, %{max_ammo: 3}}
    end

    test "the bullet count is clamped to a sane range" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("ammo-2"))
      {:ok, room} = Room.start_link(id: "ammo-2", seed: 1, bots: 0)
      Room.join(room, "alice")
      assert_receive {:lobby, %{max_ammo: 1}}

      # Absurd or sub-1 values are pulled back to the [1, 6] range.
      Room.set_max_ammo(room, 999)
      assert_receive {:lobby, %{max_ammo: 6}}
      Room.set_max_ammo(room, 0)
      assert_receive {:lobby, %{max_ammo: 1}}
    end
  end

  describe "the between-rounds lobby" do
    setup do
      {:ok, room} =
        Room.start_link(id: "lobby-1", seed: 1, bots: 0, finish_x: 2 * World.run_speed())

      Room.join(room, "alice")
      Room.join(room, "bob")
      Room.go(room)
      Room.set_verb(room, "alice", :run)
      # Finish is two run-ticks away, so alice crosses on the second tick.
      Room.tick(room)
      Room.tick(room)
      %{room: room}
    end

    test "a finish drops everyone back to the lobby — no auto-restart", %{room: room} do
      assert Room.status(room) == :waiting
    end

    test "Go starts the next round with the players still in the lobby", %{room: room} do
      :ok = Room.go(room)
      assert Room.status(room) == :running
    end

    test "a fresh round starts everyone over — scores persist, the win doesn't repeat",
         %{room: room} do
      assert Room.score(room, "alice") == 1

      Room.go(room)
      # Nobody is running this round, so it cannot immediately re-finish.
      Room.tick(room)
      assert Room.status(room) == :running
      assert Room.score(room, "alice") == 1
    end
  end
end
