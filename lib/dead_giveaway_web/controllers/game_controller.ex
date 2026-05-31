defmodule DeadGiveawayWeb.GameController do
  use DeadGiveawayWeb, :controller

  alias DeadGiveaway.Rooms

  # Code alphabet excludes easily-confused glyphs (0/O, 1/I/L) so a code read off
  # one screen and typed into another doesn't get garbled.
  @code_alphabet ~c"ABCDEFGHJKMNPQRSTUVWXYZ23456789"
  @code_length 4

  # Create a lobby: mint a fresh code not currently in use and drop the host into
  # it. `host=true` tells the client to *start* the room (the join-by-code path
  # instead requires it to already exist — see RoomChannel).
  def new(conn, _params) do
    redirect(conn, to: ~p"/play/#{fresh_code()}?#{[host: true]}")
  end

  # Join a lobby by typed code. We normalise to the code alphabet so "abcd ",
  # "ABCD", etc. all resolve to the same room; a blank code bounces home.
  def join(conn, params) do
    case normalize_code(params["code"]) do
      "" -> conn |> put_flash(:error, "Enter a lobby code to join.") |> redirect(to: ~p"/")
      code -> redirect(conn, to: ~p"/play/#{code}")
    end
  end

  # Serves the in-browser game client for a room. The room id is read by the JS
  # client to join the matching channel. `host` (from the create redirect) tells
  # the client whether to start the room or require it to already exist. Skip the
  # app content layout so the canvas can own the viewport (the root layout still
  # loads app.js/css).
  def show(conn, %{"room" => room} = params) do
    conn
    |> put_layout(false)
    |> render(:show, room: room, host: params["host"] == "true")
  end

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
