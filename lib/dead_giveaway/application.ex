defmodule DeadGiveaway.Application do
  # See https://hexdocs.pm/elixir/Application.html
  # for more information on OTP Applications
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    children = [
      DeadGiveawayWeb.Telemetry,
      DeadGiveaway.Repo,
      {DNSCluster, query: Application.get_env(:dead_giveaway, :dns_cluster_query) || :ignore},
      {Phoenix.PubSub, name: DeadGiveaway.PubSub},
      # The public-lobby directory (issue #43): public rooms track themselves here so
      # the home page can browse and join them. Needs PubSub up first.
      DeadGiveaway.Presence,
      # Rooms are looked up by id and started on demand under a dynamic supervisor.
      {Registry, keys: :unique, name: DeadGiveaway.RoomRegistry},
      {DynamicSupervisor, name: DeadGiveaway.RoomSupervisor, strategy: :one_for_one},
      # Start a worker by calling: DeadGiveaway.Worker.start_link(arg)
      # {DeadGiveaway.Worker, arg},
      # Start to serve requests, typically the last entry
      DeadGiveawayWeb.Endpoint
    ]

    # See https://hexdocs.pm/elixir/Supervisor.html
    # for other strategies and supported options
    opts = [strategy: :one_for_one, name: DeadGiveaway.Supervisor]
    Supervisor.start_link(children, opts)
  end

  # Tell Phoenix to update the endpoint configuration
  # whenever the application is updated.
  @impl true
  def config_change(changed, _new, removed) do
    DeadGiveawayWeb.Endpoint.config_change(changed, removed)
    :ok
  end
end
