defmodule DeathRaceWeb.GameControllerTest do
  use DeathRaceWeb.ConnCase, async: true

  test "GET /play/:room serves a game page mounting the requested room", %{conn: conn} do
    conn = get(conn, ~p"/play/lobby")
    body = html_response(conn, 200)

    assert body =~ ~s(id="game")
    assert body =~ ~s(data-room="lobby")
  end
end
