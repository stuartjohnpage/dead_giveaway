defmodule DeadGiveaway.RoomTest do
  use ExUnit.Case, async: true

  alias DeadGiveaway.Presence
  alias DeadGiveaway.Room
  alias DeadGiveaway.Session
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
      session = :sys.get_state(room).session
      assert Session.count(session) == 1
      assert Session.names(session) == ["alice"]
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

    test "the round ends with no winner the moment every human is out (#55)" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("wipe-1"))

      {:ok, room} = Room.start_link(id: "wipe-1", seed: 1, bots: 2)
      Room.join(room, "alice")
      Room.go(room)

      # alice (the only human) shoots her own body: every human is now out, and the
      # next tick ends the round — the bots don't get to amble on to the line.
      alice_row = :sys.get_state(room).world.slot_of["alice"]
      assert Room.fire(room, "alice", {0.0, alice_row * World.row_spacing()}) == :fired
      Room.tick(room)

      assert_receive {:round_over, :wipe, scores}, 500
      # Nobody takes the round — not even the shared Bot tally.
      assert scores["Bot"] == 0
      assert scores["alice"] == 0
      # The room is back in the lobby, not still running bots.
      assert Room.status(room) == :waiting
    end

    test "the last human standing wins on the spot (#59)" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("last-1"))

      {:ok, room} = Room.start_link(id: "last-1", seed: 1, bots: 2, max_ammo: 2)
      Room.join(room, "alice")
      Room.join(room, "bob")
      Room.go(room)

      # bob's body drops; alice is the last human alive of two, so she wins
      # immediately — no walk to the line against nothing.
      bob_row = :sys.get_state(room).world.slot_of["bob"]
      assert Room.fire(room, "alice", {0.0, bob_row * World.row_spacing()}) == :fired
      Room.tick(room)

      assert_receive {:round_over, {:winner, "alice"}, scores}, 500
      assert scores["alice"] == 1
    end

    test "a round that began solo is not an instant walkover (#59)" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("last-2"))

      {:ok, room} = Room.start_link(id: "last-2", seed: 1, bots: 2)
      Room.join(room, "alice")
      Room.go(room)
      Room.tick(room)

      # alice is the sole human and alive — but she started alone, so the round runs.
      refute_receive {:round_over, _, _}, 100
      assert Room.status(room) == :running
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

    test "a player out of lives loses their crosshair for everyone (#61)" do
      {:ok, room} = Room.start_link(id: "aim-4", seed: 1, bots: 0, max_ammo: 2)
      Room.join(room, "alice")
      Room.join(room, "bob")
      Room.go(room)

      Room.aim(room, "alice", {1.0, 2.0})
      Room.aim(room, "bob", {3.0, 4.0})
      {:ok, snap} = Room.tick(room)
      assert Map.has_key?(snap.crosshairs, "alice")
      assert Map.has_key?(snap.crosshairs, "bob")

      # alice drops bob's body; on one life he's out. His reticle goes with him even
      # though his bullets are unspent, while alice — alive and still armed — keeps hers.
      bob_row = :sys.get_state(room).world.slot_of["bob"]
      assert Room.fire(room, "alice", {0.0, bob_row * World.row_spacing()}) == :fired
      {:ok, snap2} = Room.tick(room)
      refute Map.has_key?(snap2.crosshairs, "bob")
      assert Map.has_key?(snap2.crosshairs, "alice")
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

    test "a player whose body is dropped is privately told they're out (#11)" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("out-1"))

      {:ok, room} = Room.start_link(id: "out-1", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.go(room)

      # alice is the only body; shooting her spot drops her. The room signals *her*
      # by name so the channel can forward it to her alone — peers learn nothing (§5).
      assert Room.fire(room, "alice", {0.0, 0.0}) == :fired
      assert_receive {:player_out, "alice"}, 500
    end

    test "dropping a bot body knocks no player out — no one is signalled (#11)" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("out-2"))

      {:ok, room} = Room.start_link(id: "out-2", seed: 1, bots: 1)
      Room.join(room, "alice")
      Room.go(room)

      alice_row = :sys.get_state(room).world.slot_of["alice"]
      bot_row = 1 - alice_row

      # The shot drops the bot, not a human — so although a bullet is spent, no
      # `:player_out` is emitted (the signal tracks human knock-outs, not kills).
      assert Room.fire(room, "alice", {0.0, bot_row * World.row_spacing()}) == :fired
      refute_receive {:player_out, _}, 200
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

  describe "lives (chances, DESIGN §7)" do
    test "default to one and the host's count reaches every lobby view" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("lives-1"))
      {:ok, room} = Room.start_link(id: "lives-1", seed: 1, bots: 0)
      # A fresh lobby defaults to one life — the original "shot = out" behaviour.
      Room.join(room, "alice")
      assert_receive {:lobby, %{max_chances: 1}}

      Room.set_max_chances(room, 3)
      assert_receive {:lobby, %{max_chances: 3}}
    end

    test "the life count is clamped to a sane range" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("lives-2"))
      {:ok, room} = Room.start_link(id: "lives-2", seed: 1, bots: 0)
      Room.join(room, "alice")
      assert_receive {:lobby, %{max_chances: 1}}

      Room.set_max_chances(room, 999)
      assert_receive {:lobby, %{max_chances: 5}}
      Room.set_max_chances(room, 0)
      assert_receive {:lobby, %{max_chances: 1}}
    end

    test "the life count can't change mid-round" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("lives-3"))
      {:ok, room} = Room.start_link(id: "lives-3", seed: 1, bots: 0, finish_x: 100.0)
      Room.join(room, "alice")
      Room.go(room)

      # A live round keeps the lives it started with — set_max_chances is ignored.
      Room.set_max_chances(room, 4)
      refute_receive {:lobby, %{max_chances: 4}}
    end

    test "players are privately told their starting lives when a round begins" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("lives-4"))
      {:ok, room} = Room.start_link(id: "lives-4", seed: 1, bots: 2, max_chances: 3)
      Room.join(room, "alice")
      Room.go(room)

      assert_receive {:chances, "alice", 3}
    end

    test "taking over a bot keeps the player in and refreshes their lives, no 'out'" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("lives-5"))
      {:ok, room} = Room.start_link(id: "lives-5", seed: 1, bots: 3, max_chances: 2)
      Room.join(room, "alice")
      Room.go(room)
      assert_receive {:chances, "alice", 2}

      # alice drops her own body; with a life to spare and free bots, she takes one over.
      alice_row = :sys.get_state(room).world.slot_of["alice"]
      assert Room.fire(room, "alice", {0.0, alice_row * World.row_spacing()}) == :fired

      # She's not out — she got a fresh life count instead.
      assert_receive {:chances, "alice", 1}
      refute_receive {:player_out, "alice"}, 200
    end
  end

  describe "self body-id for client-side prediction (#41)" do
    test "players are privately told which body they drive when a round begins" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("body-1"))
      {:ok, room} = Room.start_link(id: "body-1", seed: 1, bots: 2)
      Room.join(room, "alice")
      Room.go(room)

      # The signal is named so the channel forwards it to the owner alone (§5);
      # it carries alice's own entity id and nothing about anyone else's.
      assert_receive {:you_are, "alice", id}
      assert id == :sys.get_state(room).world.slot_of["alice"]
    end

    test "a takeover re-points the owner's body id (§7)" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("body-2"))
      {:ok, room} = Room.start_link(id: "body-2", seed: 1, bots: 3, max_chances: 2)
      Room.join(room, "alice")
      Room.go(room)
      assert_receive {:you_are, "alice", first}

      # alice drops her own body and inherits a bot — her client must be re-pointed
      # at the new body or it would predict (and animate) the corpse.
      assert Room.fire(room, "alice", {0.0, first * World.row_spacing()}) == :fired
      assert_receive {:you_are, "alice", second}
      assert second != first
    end

    test "a kill with no takeover re-points nothing — the id only rides a change" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("body-3"))
      {:ok, room} = Room.start_link(id: "body-3", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.go(room)
      assert_receive {:you_are, "alice", id}

      # One life: dropping her own body just puts her out; no fresh body id follows.
      assert Room.fire(room, "alice", {0.0, id * World.row_spacing()}) == :fired
      assert_receive {:player_out, "alice"}
      refute_receive {:you_are, "alice", _}, 200
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

  describe "red light / green light (#53)" do
    test "the mode defaults to classic and the host's pick reaches every lobby view" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("mode-1"))
      {:ok, room} = Room.start_link(id: "mode-1", seed: 1, bots: 0)
      Room.join(room, "alice")
      assert_receive {:lobby, %{mode: :classic}}

      Room.set_mode(room, "red_light")
      assert_receive {:lobby, %{mode: :red_light}}
    end

    test "an unknown mode is ignored, keeping the current one" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("mode-2"))
      {:ok, room} = Room.start_link(id: "mode-2", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.set_mode(room, :red_light)
      assert_receive {:lobby, %{mode: :red_light}}

      Room.set_mode(room, "speedrun")
      assert_receive {:lobby, %{mode: :red_light}}
    end

    test "the mode can't change mid-round" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("mode-3"))
      {:ok, room} = Room.start_link(id: "mode-3", seed: 1, bots: 0, finish_x: 100.0)
      Room.join(room, "alice")
      Room.go(room)

      Room.set_mode(room, :red_light)
      refute_receive {:lobby, %{mode: :red_light}}
    end

    test "a red light round's snapshots carry the watcher's light" do
      {:ok, room} = Room.start_link(id: "mode-4", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.set_mode(room, :red_light)
      Room.go(room)

      {:ok, snap} = Room.tick(room)
      assert snap.light == :green
    end

    test "a watcher kill privately knocks the walker out and cracks an anonymous shot" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("mode-5"))
      {:ok, room} = Room.start_link(id: "mode-5", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.set_mode(room, :red_light)
      Room.go(room)

      # alice walks straight through the first red's grace — the watcher drops her.
      # (Nobody fires this round, so the crack can only be the watcher's.)
      Room.set_verb(room, "alice", :walk)
      Enum.each(1..250, fn _ -> Room.tick(room) end)

      assert_receive {:player_out, "alice"}
      assert_receive :shot
    end

    test "a watcher kill with a spare life rides the same takeover signals as a shot" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("mode-6"))
      {:ok, room} = Room.start_link(id: "mode-6", seed: 1, bots: 3, max_chances: 2)
      Room.join(room, "alice")
      Room.set_mode(room, :red_light)
      Room.go(room)
      assert_receive {:you_are, "alice", first}
      assert_receive {:chances, "alice", 2}

      # She walks through the red; the watcher drops her body and the spare life
      # moves her into a bot (the room never re-asserts her verb, so the new body
      # stands still and survives).
      Room.set_verb(room, "alice", :walk)
      Enum.each(1..250, fn _ -> Room.tick(room) end)

      assert_receive {:chances, "alice", 1}
      assert_receive {:you_are, "alice", second}
      assert second != first
      refute_receive {:player_out, "alice"}, 50
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

  describe "public/private visibility (the lobby directory, #43)" do
    test "a room is private by default — absent from the directory" do
      {:ok, room} = Room.start_link(id: "vis-default", seed: 1, bots: 0)
      Room.join(room, "alice")
      assert listing("vis-default") == nil
    end

    test "the lobby broadcast carries the visibility flag (private by default)" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("vis-flag"))
      {:ok, room} = Room.start_link(id: "vis-flag", seed: 1, bots: 0)
      Room.join(room, "alice")
      assert_receive {:lobby, %{public: false}}

      Room.set_visibility(room, true)
      assert_receive {:lobby, %{public: true}}
    end

    test "going public lists the room with its summary" do
      {:ok, room} = Room.start_link(id: "vis-list", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.join(room, "bob")
      Room.set_visibility(room, true)

      assert %{code: "vis-list", host: "alice", players: 2, theme: "neon", in_progress: false} =
               listing("vis-list")
    end

    test "going private again unlists it" do
      {:ok, room} = Room.start_link(id: "vis-toggle", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.set_visibility(room, true)
      assert listing("vis-toggle")

      Room.set_visibility(room, false)
      assert listing("vis-toggle") == nil
    end

    test "a non-boolean visibility is ignored, keeping the room private" do
      {:ok, room} = Room.start_link(id: "vis-bad", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.set_visibility(room, "yes-please")
      assert listing("vis-bad") == nil
    end

    test "the listing tracks the player count and flips to in-progress for a live round" do
      {:ok, room} = Room.start_link(id: "vis-live", seed: 1, bots: 0, finish_x: 100.0)
      Room.join(room, "alice")
      Room.set_visibility(room, true)
      assert %{players: 1, in_progress: false} = listing("vis-live")

      Room.join(room, "bob")
      assert %{players: 2} = listing("vis-live")

      # A live round badges the entry in-progress rather than hiding it (the #43 decision);
      # it stays listed so a browser can still see (and queue for) the game.
      Room.go(room)
      assert %{in_progress: true} = listing("vis-live")
    end

    test "going public mid-round lists the room without pushing :lobby into the live round" do
      Phoenix.PubSub.subscribe(DeadGiveaway.PubSub, Room.topic("vis-mid"))
      {:ok, room} = Room.start_link(id: "vis-mid", seed: 1, bots: 0, finish_x: 100.0)
      Room.join(room, "alice")
      assert_receive {:lobby, _}

      Room.go(room)
      assert_receive :round_start
      assert listing("vis-mid") == nil

      # Mid-round the directory must still update (a public game stays listed, badged
      # in-progress)...
      Room.set_visibility(room, true)
      assert %{in_progress: true} = listing("vis-mid")
      # ...but no :lobby is broadcast — everyone's in-game, so re-running their lobby handler
      # under a running round would be wrong (#43 review finding).
      refute_receive {:lobby, _}, 50
    end

    test "a closed room drops out of the directory when its process dies" do
      {:ok, room} = Room.start_link(id: "vis-close", seed: 1, bots: 0)
      Room.join(room, "alice")
      Room.set_visibility(room, true)
      assert listing("vis-close")

      Room.close(room)
      # Presence cleans up on the process's :DOWN, which is async w.r.t. the stop — so a
      # recycled code never inherits a stale entry.
      assert eventually(fn -> listing("vis-close") == nil end)
    end
  end

  # This room's entry in the public directory, or nil when it isn't listed. Keyed by the
  # room id, so async tests each watching their own id don't see each other's lobbies.
  defp listing(id) do
    case Presence.list(Presence.topic()) do
      %{^id => %{metas: [meta | _]}} -> meta
      _ -> nil
    end
  end

  # Retry a predicate over a short bounded window: Presence's death-cleanup is async w.r.t.
  # a room stopping, so a just-closed lobby can briefly linger in the directory.
  defp eventually(fun, retries \\ 50) do
    cond do
      fun.() ->
        true

      retries > 0 ->
        # Sequence, don't `||`: Process.sleep/1 returns :ok (truthy), so `sleep || recurse`
        # would short-circuit and never retry — making the assertion pass vacuously.
        Process.sleep(2)
        eventually(fun, retries - 1)

      true ->
        false
    end
  end
end
