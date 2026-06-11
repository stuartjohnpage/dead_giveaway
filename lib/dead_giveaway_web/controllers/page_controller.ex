defmodule DeadGiveawayWeb.PageController do
  use DeadGiveawayWeb, :controller

  def home(conn, _params) do
    # The name this browser has claimed as a registered account (#38), or nil for a
    # guest — drives the identity card's claim affordance vs registered badge.
    render(conn, :home, registered_name: get_session(conn, :registered_name))
  end
end
