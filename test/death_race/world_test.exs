defmodule DeathRace.WorldTest do
  use ExUnit.Case, async: true

  alias DeathRace.World

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
      assert match?({:killed, _}, first)

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

      assert match?({:killed, _}, ea)
      assert match?({:killed, _}, eb)
    end

    test "a kill reveals the target was human" do
      world = World.new(seed: 1, humans: ["alice"], bots: 0)

      # Sole entity is alice at row 0 — shooting that spot is shooting herself.
      {_world, event} = World.fire(world, "alice", {0.0, 0.0})
      assert event == {:killed, :human}
    end

    test "a kill reveals the target was a bot" do
      world = World.new(seed: 1, humans: ["alice"], bots: 1)
      bot_row = 1 - world.slot_of["alice"]

      {_world, event} = World.fire(world, "alice", {0.0, bot_row * World.row_spacing()})
      assert event == {:killed, :bot}
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

    test "a player who has been shot can no longer fire" do
      world = World.new(seed: 1, humans: ["alice", "bob"], bots: 0)
      alice_row = world.slot_of["alice"]

      {world, {:killed, :human}} =
        World.fire(world, "bob", {0.0, alice_row * World.row_spacing()})

      {world2, event} = World.fire(world, "alice", {0.0, 0.0})
      assert event == :no_shot
      assert living_count(world2) == living_count(world)
    end
  end

  defp positions(world) do
    for e <- World.snapshot(world).entities, into: %{}, do: {e.id, e.x}
  end

  defp living_count(world) do
    Enum.count(World.snapshot(world).entities, & &1.alive)
  end
end
