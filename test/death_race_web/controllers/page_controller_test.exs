defmodule DeathRaceWeb.PageControllerTest do
  use DeathRaceWeb.ConnCase

  test "GET / shows the landing page with create and join options", %{conn: conn} do
    conn = get(conn, ~p"/")
    body = html_response(conn, 200)

    assert body =~ "DEATH RACE"
    assert body =~ ~s(href="/play/new")
    assert body =~ ~s(action="/join")
  end
end
