defmodule DeathRaceWeb.Router do
  use DeathRaceWeb, :router

  pipeline :browser do
    plug :accepts, ["html"]
    plug :fetch_session
    plug :fetch_live_flash
    plug :put_root_layout, html: {DeathRaceWeb.Layouts, :root}
    plug :protect_from_forgery
    plug :put_secure_browser_headers
  end

  pipeline :api do
    plug :accepts, ["json"]
  end

  scope "/", DeathRaceWeb do
    pipe_through :browser

    get "/", PageController, :home
    # `/play/new` mints a fresh lobby code (the host); `/join` takes a typed code.
    # Both resolve to `/play/:room`, so they're declared before the catch-all.
    get "/play/new", GameController, :new
    post "/join", GameController, :join
    get "/play/:room", GameController, :show
    get "/leaderboard", LeaderboardController, :index
  end

  # Other scopes may use custom stacks.
  # scope "/api", DeathRaceWeb do
  #   pipe_through :api
  # end

  # Enable LiveDashboard and Swoosh mailbox preview in development
  if Application.compile_env(:death_race, :dev_routes) do
    # If you want to use the LiveDashboard in production, you should put
    # it behind authentication and allow only admins to access it.
    # If your application does not have an admins-only section yet,
    # you can use Plug.BasicAuth to set up some basic authentication
    # as long as you are also using SSL (which you should anyway).
    import Phoenix.LiveDashboard.Router

    scope "/dev" do
      pipe_through :browser

      live_dashboard "/dashboard", metrics: DeathRaceWeb.Telemetry
      forward "/mailbox", Plug.Swoosh.MailboxPreview
    end
  end
end
