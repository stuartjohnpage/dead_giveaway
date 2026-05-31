defmodule DeathRaceWeb.LeaderboardController do
  use DeathRaceWeb, :controller

  alias DeathRace.Accounts

  def index(conn, _params) do
    render(conn, :index, players: Accounts.leaderboard())
  end
end
