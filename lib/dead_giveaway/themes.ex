defmodule DeadGiveaway.Themes do
  @moduledoc """
  The catalogue of visual/audio themes a room can wear (DESIGN §9 — cosmetic only).

  This module is the single source of truth for *which* themes exist and their
  display names — used by `Room` to validate a host's pick and by the game page to
  render the lobby's theme picker. The asset, audio, and bullet *paths* for a theme
  live in that theme's own manifest (`priv/static/themes/<key>/theme.json`), loaded
  client-side; this module deliberately knows only names, so adding a theme is "drop
  a folder under priv/static/themes/ + add one entry here".
  """

  # Order is the order shown in the picker; the head is the default for a new room.
  @catalog [
    %{key: "neon", display: "Neon Concourse"},
    %{key: "western", display: "Dead Man's Gulch"},
    %{key: "station", display: "Derelict Orbital"}
  ]

  @doc "Every theme as `%{key, display}`, in picker order."
  def all, do: @catalog

  @doc "Just the valid theme keys."
  def keys, do: Enum.map(@catalog, & &1.key)

  @doc "The default theme a fresh room starts on."
  def default, do: hd(@catalog).key

  @doc "Whether `key` names a real theme."
  def valid?(key), do: key in keys()

  @doc """
  The pack's content `version` from its `theme.json` manifest, or `nil` if absent.

  `gen_pack.py` writes this as a short hash over the pack's assets; the client appends it as
  `?v=…` to every theme asset URL, and the home page does the same for its menu backdrop, so
  regenerated art busts the browser cache (these paths are raw, not `phx.digest`'d). Returns
  `nil` for a missing/old/unparseable manifest, in which case callers serve the asset
  unversioned (correct, just not cache-busted).
  """
  def asset_version(key) do
    path = Application.app_dir(:dead_giveaway, ["priv", "static", "themes", key, "theme.json"])

    with {:ok, body} <- File.read(path),
         {:ok, %{"version" => v}} <- Jason.decode(body) do
      v
    else
      _ -> nil
    end
  end
end
