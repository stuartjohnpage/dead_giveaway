defmodule DeadGiveawayWeb.GameController do
  use DeadGiveawayWeb, :controller

  alias DeadGiveaway.{PlayerName, Rooms}

  # Code alphabet excludes easily-confused glyphs (0/O, 1/I/L) so a code read off
  # one screen and typed into another doesn't get garbled.
  @code_alphabet ~c"ABCDEFGHJKMNPQRSTUVWXYZ23456789"
  @code_length 4

  # Create a lobby: mint a fresh code not currently in use and drop the host into
  # it. Create-intent (which tells the client to *start* the room rather than
  # require it to already exist — see RoomChannel) rides the session, not the URL,
  # so the host's address bar stays a clean `/play/CODE` and the flag can't be
  # forged by editing the URL (#21).
  def new(conn, params) do
    code = fresh_code()

    conn
    |> put_session(:host_code, code)
    |> redirect(to: play_path(code, name_query(params)))
  end

  # Join a lobby by typed code. We normalise to the code alphabet so "abcd ",
  # "ABCD", etc. all resolve to the same room; a blank code bounces home.
  def join(conn, params) do
    case normalize_code(params["code"]) do
      "" -> conn |> put_flash(:error, "Enter a lobby code to join.") |> redirect(to: ~p"/")
      code -> redirect(conn, to: play_path(code, name_query(params)))
    end
  end

  # Serves the in-browser game client for a room. The room id is read by the JS
  # client to join the matching channel. Create-intent comes from the session
  # (set by `new` for the lobby's creator) and tells the client whether to start
  # the room or require it to already exist — direct navigation has no such
  # session entry, so it joins as a guest. Skip the app content layout so the
  # canvas can own the viewport (the root layout still loads app.js/css).
  def show(conn, %{"room" => room} = params) do
    conn
    |> put_layout(false)
    |> render(:show,
      room: room,
      host: get_session(conn, :host_code) == room,
      name: params["name"] || "",
      themes: DeadGiveaway.Themes.all()
    )
  end

  # A chosen name (from the splash) becomes a query param the game page reads and
  # hands to the channel on join. Blank → omitted (the room auto-names "Player N").
  defp name_query(params) do
    case PlayerName.trim(params["name"]) do
      "" -> []
      name -> [name: name]
    end
  end

  # Verified routes append a stray "?" for an empty query, so branch on it.
  defp play_path(code, []), do: ~p"/play/#{code}"
  defp play_path(code, query), do: ~p"/play/#{code}?#{query}"

  defp normalize_code(nil), do: ""

  defp normalize_code(code) do
    code
    |> String.upcase()
    |> String.replace(~r/[^A-Z0-9]/, "")
    |> String.slice(0, @code_length)
  end

  # Pick a code no live room is already using (codes are recycled once a room
  # shuts down). The alphabet gives ~810k combinations, so collisions are rare.
  defp fresh_code do
    code = random_code()
    if Rooms.whereis(code), do: fresh_code(), else: code
  end

  defp random_code do
    for _ <- 1..@code_length, into: "", do: <<Enum.random(@code_alphabet)>>
  end
end
