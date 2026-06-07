defmodule DeadGiveaway.Presence do
  @moduledoc """
  Distributed directory of currently-public lobbies (issue #43).

  A `DeadGiveaway.Room` tracks itself here on the `"lobbies"` topic while it's
  public, carrying the summary the home page lists: code, host, player count,
  theme, and whether a round is in progress. Built on `Phoenix.Presence`, so the
  bookkeeping that's awkward to do by hand comes for free:

    * a room that the host flips back to private **untracks** itself;
    * a room that closes or crashes is dropped **automatically** when its process
      dies — the directory never holds a code whose room is gone, which also means
      a recycled code (a fresh room reusing a freed one) simply tracks anew.

  The reader side is `DeadGiveawayWeb.LobbiesChannel`, which the home splash
  subscribes to for the live list.
  """
  use Phoenix.Presence,
    otp_app: :dead_giveaway,
    pubsub_server: DeadGiveaway.PubSub

  @topic "lobbies"

  @doc "The PubSub/Presence topic the public-lobby directory lives on."
  def topic, do: @topic
end
