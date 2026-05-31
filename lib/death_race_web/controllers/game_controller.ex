defmodule DeathRaceWeb.GameController do
  use DeathRaceWeb, :controller

  # Serves the in-browser game client for a room. The room id is read by the
  # JS client to join the matching channel. Skip the app content layout so the
  # canvas can own the viewport (the root layout still loads app.js/css).
  def show(conn, %{"room" => room}) do
    conn
    |> put_layout(false)
    |> render(:show, room: room)
  end
end
