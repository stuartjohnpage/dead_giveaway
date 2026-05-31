defmodule DeadGiveawayWeb.LeaderboardController do
  use DeadGiveawayWeb, :controller

  alias DeadGiveaway.Accounts

  def index(conn, _params) do
    render(conn, :index, players: Accounts.leaderboard())
  end
end
