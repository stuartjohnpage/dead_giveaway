defmodule DeadGiveawayWeb.PageControllerTest do
  use DeadGiveawayWeb.ConnCase

  test "GET / shows the landing page with create and join options", %{conn: conn} do
    conn = get(conn, ~p"/")
    body = html_response(conn, 200)

    # The hero title is split across spans ("Dead" / "Giveaway") and upper-cased in CSS,
    # so the literal "DEAD GIVEAWAY" isn't in the HTML — assert the distinctive brand word.
    assert body =~ "Giveaway"
    assert body =~ ~s(action="/play/new")
    assert body =~ ~s(action="/join")
    # The name field that feeds both create and join (skribbl-style centre block).
    assert body =~ ~s(id="player-name")
    # Audio settings are the always-accessible gear (#19), in the root layout on every page.
    assert body =~ ~s(id="audio-gear")
  end
end
