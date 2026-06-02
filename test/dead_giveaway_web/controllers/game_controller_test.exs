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

  test "GET /play/:room renders the theme picker with every catalogued theme", %{conn: conn} do
    conn = get(conn, ~p"/play/lobby")
    body = html_response(conn, 200)

    assert body =~ ~s(id="theme-select")

    for theme <- DeadGiveaway.Themes.all() do
      assert body =~ ~s(value="#{theme.key}")
      # Display names are HTML-escaped in the markup (e.g. the apostrophe in "Gulch").
      assert body =~ theme.display |> Phoenix.HTML.html_escape() |> Phoenix.HTML.safe_to_string()
    end
  end

  test "GET /play/new mints a fresh code and drops the creator in as host", %{conn: conn} do
    conn = get(conn, ~p"/play/new")

    assert %{"room" => code} =
             Regex.named_captures(~r"^/play/(?<room>[A-Z0-9]+)\?host=true$", redirected_to(conn))

    assert String.length(code) == 4
  end

  test "GET /play/new carries the chosen name through to the lobby", %{conn: conn} do
    conn = get(conn, ~p"/play/new?#{[name: "Ada"]}")
    assert redirected_to(conn) =~ ~r"\?host=true&name=Ada$"
  end

  test "POST /join normalises the code and redirects into that room", %{conn: conn} do
    conn = post(conn, ~p"/join", %{"code" => "ab2d"})
    assert redirected_to(conn) == ~p"/play/AB2D"
  end

  test "POST /join carries the chosen name through to the lobby", %{conn: conn} do
    conn = post(conn, ~p"/join", %{"code" => "AB2D", "name" => "Ada"})
    assert redirected_to(conn) == ~p"/play/AB2D?#{[name: "Ada"]}"
  end

  test "POST /join with a blank name adds no query (the room auto-names)", %{conn: conn} do
    conn = post(conn, ~p"/join", %{"code" => "AB2D", "name" => "   "})
    assert redirected_to(conn) == ~p"/play/AB2D"
  end

  test "POST /join with a blank code bounces back home with a flash", %{conn: conn} do
    conn = post(conn, ~p"/join", %{"code" => "   "})
    assert redirected_to(conn) == ~p"/"
    assert Phoenix.Flash.get(conn.assigns.flash, :error) =~ "lobby code"
  end
end
