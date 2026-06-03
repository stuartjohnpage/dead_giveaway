defmodule DeadGiveaway.WorldTest do
  use ExUnit.Case, async: true

  alias DeadGiveaway.World

  describe "spawning" do
    test "spawns one entity per character, each on its own row, all at x=0" do
      world = World.new(seed: 1, humans: ["alice", "bob"], bots: 4)
      snap = World.snapshot(world)

      assert length(snap.entities) == 6
      assert Enum.all?(snap.entities, &(&1.x == 0.0))
      assert Enum.map(snap.entities, & &1.row) |> Enum.sort() == [0, 1, 2, 3, 4, 5]
    end

    test "snapshot never reveals which entities are human" do
      world = World.new(seed: 1, humans: ["alice", "bob"], bots: 4)
      snap = World.snapshot(world)

      for entity <- snap.entities do
        refute Map.has_key?(entity, :human?)
        refute Map.has_key?(entity, :player)
      end
    end

    test "an empty world (no humans, no bots) has no entities, not phantom rows" do
      # Guards the `0..(total - 1)` range: with total == 0 that is `0..-1`, which
      # would otherwise spawn entities on rows 0 and -1.
      world = World.new(seed: 1, humans: [], bots: 0)
      assert World.snapshot(world).entities == []
    end
  end

  describe "movement" do
    test "a stopped character does not move" do
      world = World.new(seed: 1, humans: ["alice"], bots: 0)
      world = World.tick(world)

      [e] = World.snapshot(world).entities
      assert e.x == 0.0
    end

    test "a walking human advances by the walk speed each tick" do
      world = World.new(seed: 1, humans: ["alice"], bots: 0)
      world = world |> World.set_verb("alice", :walk) |> World.tick()

      [e] = World.snapshot(world).entities
      assert e.x == World.walk_speed()
      assert e.verb == :walk
    end

    test "running advances faster than any bot can ever move" do
      world = World.new(seed: 1, humans: ["alice"], bots: 0)
      world = world |> World.set_verb("alice", :run) |> World.tick()

      [e] = World.snapshot(world).entities
      assert e.x == World.run_speed()
      assert World.run_speed() > World.bot_max_speed()
    end

    test "setting a verb for a player with no body in this world is a no-op" do
      world = World.new(seed: 1, humans: ["alice"], bots: 0)

      # A mid-round joiner (§8) isn't in the world yet — their input must be
      # ignored, not raise, and must not disturb the existing entities.
      assert World.set_verb(world, "latecomer", :run) == world
    end
  end

  describe "bots" do
    defp tick_n(world, n), do: Enum.reduce(1..n, world, fn _, w -> World.tick(w) end)

    test "a bot advances down the track over time" do
      # Enough ticks to outlast a full stop phase, so it has surely moved.
      world = World.new(seed: 7, humans: [], bots: 1) |> tick_n(80)

      [bot] = World.snapshot(world).entities
      assert bot.x > 0.0
    end

    test "a moving bot moves at exactly the human walk speed (pace can't tell them apart)" do
      world = World.new(seed: 3, humans: [], bots: 6)

      # Across many ticks, every non-zero step a bot takes equals the walk speed.
      Enum.reduce(1..60, world, fn _, w ->
        before = positions(w)
        next = World.tick(w)

        for {id, x0} <- before do
          step = positions(next)[id] - x0
          assert step == 0.0 or step == World.walk_speed()
        end

        next
      end)
    end

    test "bots never move faster than the bot max speed (they cannot run)" do
      world = World.new(seed: 3, humans: [], bots: 5)

      Enum.reduce(1..50, world, fn _, w ->
        before = positions(w)
        next = World.tick(w)

        for {id, x0} <- before do
          assert positions(next)[id] - x0 <= World.bot_max_speed() + 1.0e-9
        end

        next
      end)
    end

    test "bots start and stop — they are not perpetually moving" do
      world = World.new(seed: 3, humans: [], bots: 1)

      verbs =
        Enum.map_reduce(1..50, world, fn _, w ->
          w = World.tick(w)
          [bot] = World.snapshot(w).entities
          {bot.verb, w}
        end)
        |> elem(0)

      assert :walk in verbs
      assert :stop in verbs
    end

    test "bot motion is fully deterministic for a given seed" do
      w1 = World.new(seed: 11, humans: [], bots: 4) |> tick_n(25)
      w2 = World.new(seed: 11, humans: [], bots: 4) |> tick_n(25)

      assert World.snapshot(w1) == World.snapshot(w2)
    end
  end

  describe "finish line and round outcome" do
    test "before anyone crosses, the round is unfinished with no outcome" do
      world = World.new(seed: 1, humans: ["alice"], bots: 3)

      refute World.finished?(world)
      assert World.outcome(world) == :none
    end

    test "a human crossing first wins the round" do
      world = World.new(seed: 1, humans: ["alice"], bots: 0, finish_x: 6.0)
      world = world |> World.set_verb("alice", :walk) |> tick_n(10)

      assert World.finished?(world)
      assert World.outcome(world) == {:winner, "alice"}
    end

    test "a bot crossing first is a wash (no winner)" do
      world = World.new(seed: 7, humans: [], bots: 1, finish_x: 6.0) |> tick_n(60)

      assert World.finished?(world)
      assert World.outcome(world) == :wash
    end

    test "when a human runs past a bot to the line, the human wins" do
      world = World.new(seed: 5, humans: ["alice"], bots: 1, finish_x: 10 * World.run_speed())
      world = world |> World.set_verb("alice", :run) |> tick_n(10)

      assert World.finished?(world)
      assert World.outcome(world) == {:winner, "alice"}
    end
  end

  describe "firing" do
    test "kills the character nearest the crosshair" do
      world = World.new(seed: 1, humans: ["alice", "bob"], bots: 0)

      # Both entities sit at x=0 on rows 0 and 1; aim at row 0's position.
      {world, _event} = World.fire(world, "alice", {0.0, 0.0})

      snap = World.snapshot(world)
      refute Enum.find(snap.entities, &(&1.row == 0)).alive
      assert Enum.find(snap.entities, &(&1.row == 1)).alive
    end

    test "a player has only one bullet — a second shot does nothing" do
      world = World.new(seed: 1, humans: ["alice", "bob"], bots: 0)

      {world, first} = World.fire(world, "alice", {0.0, World.row_spacing()})
      assert first == :killed

      {world2, second} = World.fire(world, "alice", {0.0, 0.0})
      assert second == :no_shot
      assert living_count(world2) == living_count(world)
    end

    test "each player has their own bullet — one firing doesn't spend another's" do
      world = World.new(seed: 1, humans: ["alice", "bob"], bots: 0)
      arow = world.slot_of["alice"]
      brow = world.slot_of["bob"]

      # alice shoots her own body; bob must still be able to fire afterwards.
      {world, ea} = World.fire(world, "alice", {0.0, arow * World.row_spacing()})
      {_world, eb} = World.fire(world, "bob", {0.0, brow * World.row_spacing()})

      assert ea == :killed
      assert eb == :killed
    end

    test "a kill reveals nothing — shooting a human body returns a bare :killed" do
      # The return must not betray that a human dropped (DESIGN §5, §10): no client
      # ever learns human-vs-bot from a shot.
      world = World.new(seed: 1, humans: ["alice"], bots: 0)

      # Sole entity is alice at row 0 — shooting that spot is shooting herself.
      {_world, event} = World.fire(world, "alice", {0.0, 0.0})
      assert event == :killed
    end

    test "a kill reveals nothing — shooting a bot body returns the same bare :killed" do
      world = World.new(seed: 1, humans: ["alice"], bots: 1)
      bot_row = 1 - world.slot_of["alice"]

      {_world, event} = World.fire(world, "alice", {0.0, bot_row * World.row_spacing()})
      assert event == :killed
    end

    test "a player can shoot themselves" do
      world = World.new(seed: 1, humans: ["alice"], bots: 0)
      alice_row = world.slot_of["alice"]

      {world, _} = World.fire(world, "alice", {0.0, alice_row * World.row_spacing()})
      refute Enum.find(World.snapshot(world).entities, &(&1.row == alice_row)).alive
    end

    test "a dead character does not move on subsequent ticks" do
      world =
        World.new(seed: 1, humans: ["alice"], bots: 0)
        |> World.set_verb("alice", :walk)

      {world, _} = World.fire(world, "alice", {0.0, 0.0})
      world = tick_n(world, 5)

      [e] = World.snapshot(world).entities
      assert e.x == 0.0
    end

    test "max_ammo lets a player fire that many times, then no more" do
      # Three bullets, three bots to spend them on. Everyone starts at x=0, so aiming
      # exactly at a bot's row drops that bot and never the shooter.
      world = World.new(seed: 1, humans: ["alice"], bots: 3, max_ammo: 3)
      alice_row = world.slot_of["alice"]
      bot_rows = Enum.reject(0..3, &(&1 == alice_row))

      assert World.ammo_left(world, "alice") == 3

      world =
        Enum.reduce(bot_rows, world, fn row, w ->
          {w, event} = World.fire(w, "alice", {0.0, row * World.row_spacing()})
          assert event == :killed
          w
        end)

      assert World.ammo_left(world, "alice") == 0
      {_world, event} = World.fire(world, "alice", {0.0, alice_row * World.row_spacing()})
      assert event == :no_shot
    end

    test "ammo defaults to a single bullet" do
      world = World.new(seed: 1, humans: ["alice", "bob"], bots: 0)
      assert World.ammo_left(world, "alice") == 1
    end

    test "a player who has been shot can no longer fire" do
      world = World.new(seed: 1, humans: ["alice", "bob"], bots: 0)
      alice_row = world.slot_of["alice"]

      {world, :killed} = World.fire(world, "bob", {0.0, alice_row * World.row_spacing()})

      {world2, event} = World.fire(world, "alice", {0.0, 0.0})
      assert event == :no_shot
      assert living_count(world2) == living_count(world)
    end
  end

  describe "armed? (who shows a crosshair, DESIGN §5)" do
    test "a player in the round with a bullet is armed" do
      world = World.new(seed: 1, humans: ["alice"], bots: 0)
      assert World.armed?(world, "alice")
    end

    test "a player not in the round is never armed" do
      world = World.new(seed: 1, humans: ["alice"], bots: 0)
      refute World.armed?(world, "stranger")
    end

    test "spending the last bullet disarms — the reticle drops" do
      world = World.new(seed: 1, humans: ["alice"], bots: 1)
      bot_row = 1 - world.slot_of["alice"]

      {world, :killed} = World.fire(world, "alice", {0.0, bot_row * World.row_spacing()})
      refute World.armed?(world, "alice")
    end

    test "a player whose body was shot stays armed while holding a bullet" do
      # Otherwise a reticle vanishing the instant a body dropped would betray that
      # body as the human's — a kill must reveal nothing (DESIGN §5).
      world = World.new(seed: 1, humans: ["alice", "bob"], bots: 0)
      alice_row = world.slot_of["alice"]

      {world, :killed} = World.fire(world, "bob", {0.0, alice_row * World.row_spacing()})

      refute World.snapshot(world).entities
             |> Enum.find(&(&1.row == alice_row))
             |> Map.fetch!(:alive)

      assert World.armed?(world, "alice")
    end
  end

  describe "chances and bot takeover (DESIGN §7)" do
    test "chances default to a single life" do
      world = World.new(seed: 1, humans: ["alice"], bots: 2)
      assert World.chances_left(world, "alice") == 1
    end

    test "with one life, a dropped player is out — no takeover" do
      world = World.new(seed: 1, humans: ["alice"], bots: 2, max_chances: 1)
      alice_row = world.slot_of["alice"]

      # alice shoots her own body (the nearest to her row at x=0).
      {world, :killed} = World.fire(world, "alice", {0.0, alice_row * World.row_spacing()})

      refute World.player_alive?(world, "alice")
      assert World.chances_left(world, "alice") == 1
      # Their slot still points at the dropped body — they didn't move into a bot.
      assert world.slot_of["alice"] == alice_row
    end

    test "with two lives, a dropped player takes over a free bot and stays in" do
      world = World.new(seed: 1, humans: ["alice"], bots: 3, max_chances: 2)
      alice_row = world.slot_of["alice"]

      {world, :killed} = World.fire(world, "alice", {0.0, alice_row * World.row_spacing()})

      # Still alive — but in a different body, with one life spent.
      assert World.player_alive?(world, "alice")
      assert World.chances_left(world, "alice") == 1
      assert world.slot_of["alice"] != alice_row

      # The old body is a corpse that no longer belongs to anyone.
      old = world.entities[alice_row]
      refute old.alive
      refute old.human?
      assert old.player == nil

      # And the player can drive their new body.
      world = world |> World.set_verb("alice", :walk) |> World.tick()
      new_row = world.slot_of["alice"]
      assert world.entities[new_row].x == World.walk_speed()
    end

    test "the taken-over body is the living bot furthest back" do
      # Spread the bots out so 'furthest back' is well-defined, with alice held at x=0.
      world =
        World.new(seed: 4, humans: ["alice"], bots: 4, max_chances: 2)
        |> tick_n(30)

      alice_row = world.slot_of["alice"]

      back_x =
        world.entities
        |> Map.values()
        |> Enum.filter(&(&1.alive and not &1.human?))
        |> Enum.map(& &1.x)
        |> Enum.min()

      {world, :killed} = World.fire(world, "alice", {0.0, alice_row * World.row_spacing()})

      new_row = world.slot_of["alice"]
      assert new_row != alice_row
      assert world.entities[new_row].x == back_x
    end

    test "spending the last life puts you out, even with free bots left" do
      # Two bullets so she can fire the two self-shots this exercise needs.
      world = World.new(seed: 1, humans: ["alice"], bots: 4, max_ammo: 2, max_chances: 2)

      # First drop: takeover (2 → 1 life).
      arow = world.slot_of["alice"]
      {world, :killed} = World.fire(world, "alice", {0.0, arow * World.row_spacing()})
      assert World.player_alive?(world, "alice")

      # Second drop: out of lives, so out for the round despite bots still being free.
      arow2 = world.slot_of["alice"]
      {world, :killed} = World.fire(world, "alice", {0.0, arow2 * World.row_spacing()})
      refute World.player_alive?(world, "alice")
    end

    test "with lives left but no free bot, a dropped player is out (life not spent)" do
      # Sole character is alice — there's no bot to inherit, so she's out for the round.
      world = World.new(seed: 1, humans: ["alice"], bots: 0, max_chances: 3)

      {world, :killed} = World.fire(world, "alice", {0.0, 0.0})

      refute World.player_alive?(world, "alice")
      # No takeover happened, so no life was spent.
      assert World.chances_left(world, "alice") == 3
    end

    test "a taken-over player keeps their remaining ammo" do
      # Two bullets, two lives: spend one bullet to drop her own first body, take over a
      # bot, and she should still hold the second bullet in the new body.
      world = World.new(seed: 1, humans: ["alice"], bots: 3, max_ammo: 2, max_chances: 2)
      arow = world.slot_of["alice"]

      assert World.ammo_left(world, "alice") == 2
      {world, :killed} = World.fire(world, "alice", {0.0, arow * World.row_spacing()})

      assert World.player_alive?(world, "alice")
      assert World.ammo_left(world, "alice") == 1
      assert World.armed?(world, "alice")
    end
  end

  defp positions(world) do
    for e <- World.snapshot(world).entities, into: %{}, do: {e.id, e.x}
  end

  defp living_count(world) do
    Enum.count(World.snapshot(world).entities, & &1.alive)
  end
end
