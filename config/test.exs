import Config

# Configure your database
#
# The MIX_TEST_PARTITION environment variable can be used
# to provide built-in test partitioning in CI environment.
# Run `mix help test` for more information.
config :dead_giveaway, DeadGiveaway.Repo,
  username: "postgres",
  password: "postgres",
  hostname: "localhost",
  database: "dead_giveaway_test#{System.get_env("MIX_TEST_PARTITION")}",
  pool: Ecto.Adapters.SQL.Sandbox,
  pool_size: System.schedulers_online() * 2

# We don't run a server during test. If one is required,
# you can enable the server option below.
config :dead_giveaway, DeadGiveawayWeb.Endpoint,
  http: [ip: {127, 0, 0, 1}, port: 4002],
  secret_key_base: "+Xm1Ghixf1+PIpjcXeJkd2SZoSf1T3DyX0oHkrawnHgvzg8xlf/iG9StjCX271wE",
  server: false

# Deterministic rooms for channel tests: a fast tick and no bots, so snapshots
# contain only the joined humans.
config :dead_giveaway, :room, tick_ms: 20, bots: 0, stats: nil

# In test we don't send emails
config :dead_giveaway, DeadGiveaway.Mailer, adapter: Swoosh.Adapters.Test

# Disable swoosh api client as it is only required for production adapters
config :swoosh, :api_client, false

# Print only warnings and errors during test
config :logger, level: :warning

# Initialize plugs at runtime for faster test compilation
config :phoenix, :plug_init_mode, :runtime

# Enable helpful, but potentially expensive runtime checks
config :phoenix_live_view,
  enable_expensive_runtime_checks: true

# Sort query params output of verified routes for robust url comparisons
config :phoenix,
  sort_verified_routes_query_params: true
