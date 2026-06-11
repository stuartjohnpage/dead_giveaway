defmodule DeadGiveaway.PlayerName do
  @moduledoc """
  The bounds of the one piece of free text players control — their name.

  A name is whitespace-trimmed and capped at `max_length/0` characters. This is the
  single source for that rule on the server: the game controller (building the
  `?name=` param) and the room channel (normalising + profanity-redacting an inbound
  name) both go through `trim/1`, so the cap can't drift between the two paths.

  The client mirrors `max_length/0` in two spots it can't share an Elixir constant
  with — the splash field's `maxlength` (home.html.heex) and `MAX` in identity.mjs —
  but the server trims again here regardless, so those are conveniences, not the
  authority.
  """

  @max_length 16

  @doc "The maximum number of characters a player name may have."
  def max_length, do: @max_length

  @doc """
  Trim surrounding whitespace and cap to `max_length/0`. Accepts any term (a missing
  or non-string name coerces to `""`), so callers can hand it raw params.
  """
  def trim(name) do
    name |> to_string() |> String.trim() |> String.slice(0, @max_length)
  end

  @doc """
  The full inbound chokepoint for a chosen name: `trim/1`, then profanity-redact
  (#13); a blank name becomes `nil` (callers fall back to auto-naming, or reject).
  The room channel's join/rename and the account claim flow (#38) all go through
  here, so the filter can't drift between paths.
  """
  def normalize(name) do
    case trim(name) do
      "" -> nil
      n -> DeadGiveaway.Profanity.redact(n)
    end
  end
end
