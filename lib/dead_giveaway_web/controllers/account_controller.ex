defmodule DeadGiveawayWeb.AccountController do
  @moduledoc """
  Claim-a-name onboarding (#38, DESIGN §9): guest play stays the default — name only,
  jump straight in — but a player can claim their splash name as a registered account,
  and from then on the wins recorded under that name persist to the leaderboard (§8 —
  wins only score, and only for registered names; `Room` already routes every winner
  through `Accounts.record_win/1`, which ignores guests). The claim is remembered in
  the browser session so the splash can show the registered state.
  """

  use DeadGiveawayWeb, :controller

  alias DeadGiveaway.{Accounts, PlayerName}

  def claim(conn, params) do
    # The same trim/profanity chokepoint a lobby join goes through, so the name on the
    # leaderboard is exactly the name a lobby would have seated.
    case PlayerName.normalize(params["name"]) do
      nil -> finish(conn, :error, "Type a name first, then claim it.")
      name -> claim_name(conn, name)
    end
  end

  defp claim_name(conn, name) do
    case Accounts.register_player(name) do
      {:ok, player} ->
        conn
        |> put_session(:registered_name, player.name)
        |> finish(:info, "#{player.name} is yours — wins now count on the leaderboard.")

      {:error, _changeset} ->
        # Already in the players table. If this browser made the claim, treat the
        # re-claim as a friendly no-op; otherwise the name belongs to someone else.
        if get_session(conn, :registered_name) == name do
          finish(conn, :info, "#{name} is already yours.")
        else
          finish(conn, :error, "#{name} is already claimed — pick another name.")
        end
    end
  end

  defp finish(conn, kind, message) do
    conn |> put_flash(kind, message) |> redirect(to: ~p"/")
  end
end
