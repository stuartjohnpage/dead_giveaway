defmodule DeadGiveawayWeb.PageController do
  use DeadGiveawayWeb, :controller

  def home(conn, _params) do
    # The splash always wears the neon menu backdrop. Append the pack's content version so a
    # regenerated menu_bg busts returning visitors' browser cache (raw path, not phx.digest'd).
    v = DeadGiveaway.Themes.asset_version("neon")
    menu_bg = "/themes/neon/menu_bg.png" <> if(v, do: "?v=#{v}", else: "")
    render(conn, :home, menu_bg: menu_bg)
  end
end
