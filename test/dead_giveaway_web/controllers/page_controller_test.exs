defmodule DeadGiveawayWeb.PageControllerTest do
  use DeadGiveawayWeb.ConnCase

  test "GET / shows the landing page with create and join options", %{conn: conn} do
    conn = get(conn, ~p"/")
    body = html_response(conn, 200)

    assert body =~ "DEAD GIVEAWAY"
    assert body =~ ~s(action="/play/new")
    assert body =~ ~s(action="/join")
    # The name field that feeds both create and join (skribbl-style centre block).
    assert body =~ ~s(id="player-name")
  end
end
