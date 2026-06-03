defmodule DeadGiveaway.Profanity do
  @moduledoc """
  Redacts profanity in player-supplied names — the only free text other players see
  (the lobby roster and the scoreboard show whatever name you pick; DESIGN §5/§8).

  A small curated blocklist of strong profanity is matched case-insensitively and is
  tolerant of common leetspeak (`sh1t`, `b1tch`, `fvck`); each match is replaced with
  `*` of the same length. Matching is substring-based, so profanity glued into a single
  handle (`shithead` → `****head`) is still caught — that's the common case for a
  username, where there's no whitespace to lean on.

  Pure and server-side, so it runs wherever a name is assigned (`DeadGiveaway.Room`),
  not only in the web layer — a crafted client/websocket payload can't route around it.

  Deliberately conservative. The list is short and skewed to longer, strong words so an
  innocent handle rarely contains one by accident; the known cost of substring matching
  is the "Scunthorpe problem" (an innocent word that literally spells a blocked one
  inside it — e.g. the town `Scunthorpe` → `S****horpe`), which we accept as implausible
  for a self-chosen handle. Smarter detection (dictionary-aware boundaries, wider
  leet/elongation coverage) is future work — see the originating issue.
  """

  # Base forms, lowercase; strong profanity only (mild words are intentionally omitted).
  @words ~w(fuck shit bitch cunt asshole bastard dickhead motherfucker wanker bollocks)

  # Per-character alternates so basic leetspeak is still caught; a char not listed
  # matches only itself. Kept to single characters (no elongation) so a doubled letter
  # in an innocent name — `shiitake` — doesn't get swept in.
  @leet %{
    "a" => "a@4",
    "b" => "b8",
    "c" => "c(",
    "e" => "e3",
    "g" => "g9",
    "i" => "i1!",
    "l" => "l1",
    "o" => "o0",
    "s" => "s$5",
    "t" => "t7",
    "u" => "uv"
  }

  # Built at compile time: each word becomes a sequence of one-char classes (with its
  # leet alternates), the words joined into one alternation. Computed here rather than
  # hand-written so the blocklist above stays the single source of truth.
  @source @words
          |> Enum.map(fn word ->
            word
            |> String.graphemes()
            |> Enum.map_join(fn ch -> "[" <> Regex.escape(Map.get(@leet, ch, ch)) <> "]" end)
          end)
          |> Enum.join("|")

  @doc "Replace any profanity in `name` with `*` of equal length; innocent text is untouched."
  def clean(name) when is_binary(name) do
    Regex.replace(regex(), name, &String.duplicate("*", String.length(&1)))
  end

  @doc "True when `name` contains a blocked word (matched as in `clean/1`)."
  def profane?(name) when is_binary(name), do: Regex.match?(regex(), name)

  defp regex, do: Regex.compile!("(?:" <> @source <> ")", "iu")
end
