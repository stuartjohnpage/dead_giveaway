defmodule DeadGiveaway.Repo do
  use Ecto.Repo,
    otp_app: :dead_giveaway,
    adapter: Ecto.Adapters.Postgres
end
