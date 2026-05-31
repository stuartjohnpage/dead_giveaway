defmodule DeadGiveaway.Repo.Migrations.CreatePlayers do
  use Ecto.Migration

  def change do
    create table(:players) do
      add :name, :string, null: false
      add :wins, :integer, null: false, default: 0

      timestamps(type: :utc_datetime)
    end

    create unique_index(:players, [:name])
  end
end
