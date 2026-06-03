defmodule DeadGiveaway.Profanity do
  @moduledoc """
  Server-side profanity redaction for player-supplied names (#13).

  A name is the only free text players control, and it's shown to the whole lobby and the
  scoreboard, so we mask slurs/swears before the name is stored or broadcast. This runs
  from `DeadGiveawayWeb.RoomChannel.normalize_name/1` — the single server-side chokepoint
  every join flows through — so a crafted client/websocket payload can't slip one past it.

  Detection folds common leetspeak (`4→a 3→e 1→i 0→o 5→s 7→t @→a $→s`) and ASCII case into
  a **1:1 codepoint map** — no codepoints added or removed — so a match in the normalised
  form lines up position-for-position with the original. That lets us mask exactly the
  offending characters (`Sh1tLord` → `****Lord`) instead of nuking the whole name.

  The Scunthorpe problem (an innocent word that merely *contains* a bad substring) is held
  off with a small allowlist of whole tokens that are never redacted. This is deliberately
  cheap (it runs on every join) and imperfect — a curated wordlist, not a maintained
  library; revisit if any other free-text input is ever added.
  """

  # Lowercased, de-leeted base forms. Kept short and focused on the worst words so that
  # substring matching produces few false positives.
  @words ~w(
    fuck shit cunt bitch bastard asshole dick cock pussy slut whore wank
    nigger nigga faggot fag retard rape nazi
  )c

  # Whole normalised tokens that legitimately contain a listed word as a substring and so
  # must never be masked (the Scunthorpe problem).
  @allowlist ~w(scunthorpe assassin assassins assemble class classic glass grass pass)

  # 1:1 leetspeak fold, applied after ASCII-lowercasing. Keys are already-lowercase
  # symbols/digits, so order doesn't matter.
  @leet %{?4 => ?a, ?3 => ?e, ?1 => ?i, ?0 => ?o, ?5 => ?s, ?7 => ?t, ?@ => ?a, ?$ => ?s}

  @doc """
  Mask any profanity in `name`, preserving its length, casing and non-offending parts.
  Returns the name unchanged when it's clean (or is an allowlisted token).
  """
  def redact(name) when is_binary(name) do
    orig = String.to_charlist(name)
    norm = Enum.map(orig, &normalize/1)

    # A single innocent token that happens to contain a bad substring — leave it be.
    if alnum(norm) in @allowlist do
      name
    else
      masked = mask_indices(norm)

      orig
      |> Enum.with_index()
      |> Enum.map(fn {c, i} -> if MapSet.member?(masked, i), do: ?*, else: c end)
      |> List.to_charlist()
      |> List.to_string()
    end
  end

  # Fold one codepoint: ASCII upper→lower, then the leet map; everything else untouched.
  defp normalize(c) do
    lower = if c in ?A..?Z, do: c + 32, else: c
    Map.get(@leet, lower, lower)
  end

  # The set of character indices covered by any wordlist match in the normalised name.
  defp mask_indices(norm) do
    n = length(norm)

    Enum.reduce(@words, MapSet.new(), fn word, acc ->
      len = length(word)

      Enum.reduce(0..max(n - len, 0), acc, fn i, acc ->
        if i + len <= n and Enum.slice(norm, i, len) == word do
          Enum.reduce(i..(i + len - 1), acc, &MapSet.put(&2, &1))
        else
          acc
        end
      end)
    end)
  end

  # The normalised name reduced to its a–z/0–9 run, for the allowlist comparison.
  defp alnum(norm) do
    norm
    |> Enum.filter(&(&1 in ?a..?z or &1 in ?0..?9))
    |> List.to_string()
  end
end
