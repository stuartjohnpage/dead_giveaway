defmodule DeadGiveawayWeb.LobbiesChannel do
  @moduledoc """
  Read side of the public-lobby directory (issue #43).

  The home splash joins `"lobbies"` to browse currently-public rooms and keep the
  list live. On join we push the current set; thereafter every `presence_diff`
  (rooms opening, filling, starting a round, or closing) re-pushes the whole set.

  The list is small — a handful of public lobbies — so we ship the full set on each
  change and let the client just replace its list, rather than applying diffs
  client-side. Read-only: joining here never starts or mutates a room; the actual
  join still goes through the normal `/play/:code` flow.
  """
  use Phoenix.Channel

  alias DeadGiveaway.Presence

  # Intercept Presence's own diff so we can collapse it into a single `"lobbies"` push of
  # the full set, instead of leaking raw presence_diff payloads to the browser.
  intercept(["presence_diff"])

  @impl true
  def join("lobbies", _payload, socket) do
    # Push the initial set after join completes (we can't push from within join/3).
    send(self(), :after_join)
    {:ok, socket}
  end

  @impl true
  def handle_info(:after_join, socket) do
    push(socket, "lobbies", %{lobbies: list_lobbies()})
    {:noreply, socket}
  end

  @impl true
  def handle_out("presence_diff", _diff, socket) do
    push(socket, "lobbies", %{lobbies: list_lobbies()})
    {:noreply, socket}
  end

  # Flatten the Presence map into the plain list the client renders: one row per public
  # room. A room tracks a single entry, so we take the head meta. Ordered waiting-first,
  # then fullest, then by code for a stable sort — so a joinable, busy lobby leads.
  defp list_lobbies do
    Presence.list(Presence.topic())
    |> Enum.map(fn {code, %{metas: [meta | _]}} ->
      %{
        code: code,
        host: meta.host,
        players: meta.players,
        theme: meta.theme,
        in_progress: meta.in_progress
      }
    end)
    |> Enum.sort_by(fn l -> {l.in_progress, -l.players, l.code} end)
  end
end
