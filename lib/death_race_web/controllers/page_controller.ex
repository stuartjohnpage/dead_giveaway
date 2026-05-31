defmodule DeathRaceWeb.PageController do
  use DeathRaceWeb, :controller

  def home(conn, _params) do
    render(conn, :home)
  end
end
