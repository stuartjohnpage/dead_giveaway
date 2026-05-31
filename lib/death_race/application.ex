defmodule DeathRace.Application do
  # See https://hexdocs.pm/elixir/Application.html
  # for more information on OTP Applications
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    children = [
      DeathRaceWeb.Telemetry,
      DeathRace.Repo,
      {DNSCluster, query: Application.get_env(:death_race, :dns_cluster_query) || :ignore},
      {Phoenix.PubSub, name: DeathRace.PubSub},
      # Rooms are looked up by id and started on demand under a dynamic supervisor.
      {Registry, keys: :unique, name: DeathRace.RoomRegistry},
      {DynamicSupervisor, name: DeathRace.RoomSupervisor, strategy: :one_for_one},
      # Start a worker by calling: DeathRace.Worker.start_link(arg)
      # {DeathRace.Worker, arg},
      # Start to serve requests, typically the last entry
      DeathRaceWeb.Endpoint
    ]

    # See https://hexdocs.pm/elixir/Supervisor.html
    # for other strategies and supported options
    opts = [strategy: :one_for_one, name: DeathRace.Supervisor]
    Supervisor.start_link(children, opts)
  end

  # Tell Phoenix to update the endpoint configuration
  # whenever the application is updated.
  @impl true
  def config_change(changed, _new, removed) do
    DeathRaceWeb.Endpoint.config_change(changed, removed)
    :ok
  end
end
