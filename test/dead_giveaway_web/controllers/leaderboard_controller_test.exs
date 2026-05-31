defmodule DeadGiveawayWeb.LeaderboardControllerTest do
  use DeadGiveawayWeb.ConnCase, async: true

  alias DeadGiveaway.Accounts

  test "GET /leaderboard shows registered players and their wins", %{conn: conn} do
    {:ok, _} = Accounts.register_player("alice")
    Accounts.record_win("alice")

    conn = get(conn, ~p"/leaderboard")
    body = html_response(conn, 200)

    assert body =~ "Leaderboard"
    assert body =~ "alice"
    assert body =~ "1"
  end
end
