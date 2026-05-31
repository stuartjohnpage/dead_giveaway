defmodule DeadGiveawayWeb.GameControllerTest do
  use DeadGiveawayWeb.ConnCase, async: true

  test "GET /play/:room serves a game page mounting the requested room", %{conn: conn} do
    conn = get(conn, ~p"/play/lobby")
    body = html_response(conn, 200)

    assert body =~ ~s(id="game")
    assert body =~ ~s(data-room="lobby")
    # Direct navigation isn't the host — joining requires the room to exist.
    assert body =~ ~s(data-host="false")
  end

  test "GET /play/new mints a fresh code and drops the creator in as host", %{conn: conn} do
    conn = get(conn, ~p"/play/new")

    assert %{"room" => code} =
             Regex.named_captures(~r"^/play/(?<room>[A-Z0-9]+)\?host=true$", redirected_to(conn))

    assert String.length(code) == 4
  end

  test "POST /join normalises the code and redirects into that room", %{conn: conn} do
    conn = post(conn, ~p"/join", %{"code" => "ab2d"})
    assert redirected_to(conn) == ~p"/play/AB2D"
  end

  test "POST /join with a blank code bounces back home with a flash", %{conn: conn} do
    conn = post(conn, ~p"/join", %{"code" => "   "})
    assert redirected_to(conn) == ~p"/"
    assert Phoenix.Flash.get(conn.assigns.flash, :error) =~ "lobby code"
  end
end
