defmodule DeadGiveaway.ProfanityTest do
  use ExUnit.Case, async: true

  alias DeadGiveaway.Profanity

  describe "clean/1" do
    test "redacts a blocked word with stars of equal length" do
      assert Profanity.clean("fuck") == "****"
    end

    test "leaves innocent names untouched" do
      assert Profanity.clean("alice") == "alice"
      assert Profanity.clean("Player 1") == "Player 1"
    end

    test "is case-insensitive" do
      assert Profanity.clean("SHIT") == "****"
      assert Profanity.clean("BiTcH") == "*****"
    end

    test "catches common leetspeak substitutions" do
      assert Profanity.clean("sh1t") == "****"
      assert Profanity.clean("b1tch") == "*****"
      assert Profanity.clean("fvck") == "****"
    end

    test "redacts only the offending span inside a longer single-token handle" do
      assert Profanity.clean("shithead") == "****head"
      assert Profanity.clean("xXfuckXx") == "xX****Xx"
    end

    test "redacts every occurrence" do
      assert Profanity.clean("fuck shit") == "**** ****"
    end

    test "does not flag innocent names that merely double a letter (no elongation)" do
      # 'shiitake' must not trip the 'shit' rule — the matcher is single-char, not greedy.
      assert Profanity.clean("shiitake") == "shiitake"
    end
  end

  describe "profane?/1" do
    test "true when a blocked word is present, false otherwise" do
      assert Profanity.profane?("a fuck b")
      assert Profanity.profane?("sh1tposter")
      refute Profanity.profane?("hello world")
      refute Profanity.profane?("Player 2")
    end
  end
end
