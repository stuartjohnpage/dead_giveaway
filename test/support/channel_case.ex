defmodule DeadGiveawayWeb.ChannelCase do
  @moduledoc """
  Test case for channels — sets up `Phoenix.ChannelTest` against the app endpoint.
  Channels here don't touch the database, so no Ecto sandbox is needed.
  """

  use ExUnit.CaseTemplate

  using do
    quote do
      import Phoenix.ChannelTest
      import DeadGiveawayWeb.ChannelCase

      @endpoint DeadGiveawayWeb.Endpoint
    end
  end
end
