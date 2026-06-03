defmodule DeadGiveaway.ProfanityTest do
  use ExUnit.Case, async: true

  alias DeadGiveaway.Profanity

  test "a clean name is returned untouched" do
    assert Profanity.redact("Ada Lovelace") == "Ada Lovelace"
    assert Profanity.redact("Player 3") == "Player 3"
  end

  test "masks an offending word in place, preserving the rest and its length" do
    out = Profanity.redact("ShitLord")
    assert out == "****Lord"
    assert String.length(out) == String.length("ShitLord")
  end

  test "sees through leetspeak (digits and symbol substitutions)" do
    assert Profanity.redact("Sh1tLord") == "****Lord"
    assert Profanity.redact("b1tch") == "*****"
    assert Profanity.redact("@sshole") == "*******"
  end

  test "is case-insensitive but keeps the surrounding original casing" do
    assert Profanity.redact("BIGShitENERGY") == "BIG****ENERGY"
  end

  test "does not redact innocent words that merely contain a bad substring (Scunthorpe)" do
    assert Profanity.redact("Scunthorpe") == "Scunthorpe"
    assert Profanity.redact("assassin") == "assassin"
    assert Profanity.redact("classic") == "classic"
  end

  test "a wholly profane name becomes fully masked (still non-blank)" do
    out = Profanity.redact("fuck")
    assert out == "****"
    refute out == ""
  end

  test "masks every occurrence when a word repeats" do
    assert Profanity.redact("shitshit") == "********"
  end
end
