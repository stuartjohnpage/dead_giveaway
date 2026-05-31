defmodule DeathRaceWeb.UserSocket do
  use Phoenix.Socket

  # All game traffic flows over per-room channels.
  channel "room:*", DeathRaceWeb.RoomChannel

  @impl true
  def connect(_params, socket, _connect_info), do: {:ok, socket}

  # Guests are anonymous for now; no persistent socket identity.
  @impl true
  def id(_socket), do: nil
end
