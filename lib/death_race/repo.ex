defmodule DeathRace.Repo do
  use Ecto.Repo,
    otp_app: :death_race,
    adapter: Ecto.Adapters.Postgres
end
