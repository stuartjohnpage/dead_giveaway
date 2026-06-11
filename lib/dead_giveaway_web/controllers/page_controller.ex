defmodule DeadGiveawayWeb.PageController do
  use DeadGiveawayWeb, :controller

  def home(conn, _params) do
    render(conn, :home)
  end
end
