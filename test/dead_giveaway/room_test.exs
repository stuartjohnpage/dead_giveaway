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
      assert {:ok, 0, "alice", _host?} = Room.join(room, "alice")
    end

    test "assigns sequential slots to subsequent players" do
      {:ok, room} = Room.start_link(id: "r1")
      assert {:ok, 0, "alice", _} = Room.join(room, "alice")
      assert {:ok, 1, "bob", _} = Room.join(room, "bob")
      assert {:ok, 2, "carol", _} = Room.join(room, "carol")
    end

    test "auto-names players Player N when no name is given" do
      {:ok, room} = Room.start_link(id: "r1")
      assert {:ok, 0, "Player 1", _} = Room.join(room)
      assert {:ok, 1, "Player 2", _} = Room.join(room)
    end

    test "disambiguates an explicit name already taken so two players never collapse" do
      {:ok, room} = Room.start_link(id: "r1")
      assert {:ok, 0, "guest", _} = Room.join(room, "guest")
      assert {:ok, 1, "guest (2)", _} = Room.join(room, "guest")
      assert {:ok, 2, "guest (3)", _} = Room.join(room, "guest")
    end

    test "auto-names reuse the lowest free number so the count doesn't climb on (re)joins" do
      {:ok, room} = Room.start_link(id: "rejoin-1")
      {:ok, _, "Player 1", _} = Room.join(room)
      {:ok, _, "Player 2", _} = Room.join(room)
      {:ok, _, "Player 3", _} = Room.join(room)

      # Player 2 leaves, freeing the number 2. The next auto-named joiner takes it
      # back rather than becoming "Player 4" — so refreshes don't ratchet the count up.
      :ok = Room.leave(room, "Player 2")
      assert {:ok, _, "Player 2", _} = Room.join(room)
    end
  end

  describe "the host" do
    test "is the first player to join; everyone after is a guest" do
      {:ok, room} = Room.start_link(id: "host-1")
      assert {:ok, _, "alice", true} = Room.join(room, "alice")
      assert {:ok, _, "bob", false} = Room.join(room, "bob")
      assert {:ok, _, "carol", false} = Room.join(room, "carol")
    end

    test "hands off to the earliest remaining joiner when the host leaves" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("host-2"))
      {:ok, room} = Room.start_link(id: "host-2")
      {:ok, _, "alice", true} = Room.join(room, "alice")
      {:ok, _, "bob", false} = Room.join(room, "bob")
      {:ok, _, "carol", false} = Room.join(room, "carol")

      # The host leaving promotes bob (the next-lowest slot), broadcast to everyone.
      :ok = Room.leave(room, "alice")
      assert_receive {:lobby, %{host: "bob"}}
      assert :sys.get_state(room).host == "bob"
    end

    test "a leaver's win tally is cleared so a reused name doesn't inherit it" do
      {:ok, room} =
        Room.start_link(id: "score-reuse", seed: 1, bots: 0, finish_x: 2 * World.run_speed())

      {:ok, _, "Player 1", _} = Room.join(room)
      {:ok, _, "Player 2", _} = Room.join(room)
      Room.go(room)
      # Player 1 runs across the finish (two run-ticks away) and banks a win.
      Room.set_verb(room, "Player 1", :run)
      Room.tick(room)
      Room.tick(room)
      assert Room.score(room, "Player 1") == 1

      # Player 1 leaves; the freed "Player 1" number is handed to the next joiner, who
      # must start from zero rather than inheriting the departed player's win.
      :ok = Room.leave(room, "Player 1")
      {:ok, _, "Player 1", _} = Room.join(room)
      assert Room.score(room, "Player 1") == 0
    end

    test "a guest leaving never changes who hosts" do
      {:ok, room} = Room.start_link(id: "host-3")
      Room.join(room, "alice")
      Room.join(room, "bob")

      :ok = Room.leave(room, "bob")
      assert :sys.get_state(room).host == "alice"
    end

    test "is cleared once the room empties" do
      {:ok, room} = Room.start_link(id: "host-4")
      Room.join(room, "alice")
      :ok = Room.leave(room, "alice")
      assert :sys.get_state(room).host == nil
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
      {:ok, 0, _, _} = Room.join(room, "alice")
      {:ok, 1, _, _} = Room.join(room, "bob")
      :ok = Room.leave(room, "alice")
      # Next joiner must not reuse slot 0 (alice's old slot is gone) AND must not
      # land on bob's slot 1.
      assert {:ok, 2, "carol", _} = Room.join(room, "carol")
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
      {:ok, _, "bob", _} = Room.join(room, "bob")
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
      {:ok, _, "carol", _} = Room.join(room, "carol")
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

  describe "crosshairs riding the snapshot (DESIGN §5)" do
    test "a player's aim shows up in the snapshot while they're armed" do
      {:ok, room} = Room.start_link(id: "aim-1", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.join(room, "bob")
      Room.go(room)

      Room.aim(room, "alice", {3.0, 4.0})
      {:ok, snap} = Room.tick(room)

      assert snap.crosshairs["alice"] == %{x: 3.0, y: 4.0}
    end

    test "a crosshair disappears once its owner spends their last bullet" do
      {:ok, room} = Room.start_link(id: "aim-2", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.go(room)

      Room.aim(room, "alice", {0.0, 0.0})
      {:ok, snap} = Room.tick(room)
      assert Map.has_key?(snap.crosshairs, "alice")

      # Her one bullet spent (the sole body is her own), she's unarmed — reticle gone.
      Room.fire(room, "alice", {0.0, 0.0})
      {:ok, snap2} = Room.tick(room)
      refute Map.has_key?(snap2.crosshairs, "alice")
    end

    test "an aim sent outside a live round is dropped, not stashed" do
      {:ok, room} = Room.start_link(id: "aim-3", seed: 1, bots: 0)
      Room.join(room, "alice")

      # No Go — the world is nil, so a stray lobby aim doesn't accumulate.
      Room.aim(room, "alice", {1.0, 2.0})
      assert :sys.get_state(room).crosshairs == %{}
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

  describe "the room's theme" do
    test "defaults to the catalogue head and the host's pick reaches every lobby view" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("theme-1"))
      {:ok, room} = Room.start_link(id: "theme-1", seed: 1, bots: 0)
      # A fresh lobby wears the default theme.
      Room.join(room, "alice")
      assert_receive {:lobby, %{theme: "neon"}}

      # The host switching it re-broadcasts the roster carrying the new theme.
      Room.set_theme(room, "western")
      assert_receive {:lobby, %{theme: "western"}}
    end

    test "an unknown theme is ignored, keeping the current one" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("theme-2"))
      {:ok, room} = Room.start_link(id: "theme-2", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.set_theme(room, "western")
      assert_receive {:lobby, %{theme: "western"}}

      # A stale/hand-crafted key can't strand the room on a missing pack.
      Room.set_theme(room, "no-such-theme")
      assert_receive {:lobby, %{theme: "western"}}
    end

    test "the theme can't change mid-round" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("theme-3"))
      {:ok, room} = Room.start_link(id: "theme-3", seed: 1, bots: 0, finish_x: 100.0)
      Room.join(room, "alice")
      Room.go(room)

      # A live round keeps the look it started with — set_theme is a no-op (no lobby
      # broadcast carrying the change) until the round ends.
      Room.set_theme(room, "western")
      refute_receive {:lobby, %{theme: "western"}}
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
