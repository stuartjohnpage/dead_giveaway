defmodule DeathRace.Accounts.Player do
  @moduledoc "A registered player whose cumulative wins persist across sessions (§8)."

  use Ecto.Schema
  import Ecto.Changeset

  schema "players" do
    field :name, :string
    field :wins, :integer, default: 0

    timestamps(type: :utc_datetime)
  end

  def registration_changeset(player, attrs) do
    player
    |> cast(attrs, [:name])
    |> validate_required([:name])
    |> validate_length(:name, min: 1, max: 40)
    |> unique_constraint(:name)
  end
end
