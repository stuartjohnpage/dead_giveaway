defmodule DeadGiveawayWeb.AccountControllerTest do
  use DeadGiveawayWeb.ConnCase, async: true

  alias DeadGiveaway.Accounts

  test "POST /claim registers the name and remembers it in the session (#38)", %{conn: conn} do
    conn = post(conn, ~p"/claim", %{"name" => "  alice  "})

    assert redirected_to(conn) == ~p"/"
    assert get_session(conn, :registered_name) == "alice"
    assert Phoenix.Flash.get(conn.assigns.flash, :info) =~ "alice is yours"
    # The claim is what makes wins persist: record_win now credits instead of ignoring.
    assert {:ok, %{wins: 1}} = Accounts.record_win("alice")
  end

  test "the claim passes the profanity chokepoint like a join (#13)", %{conn: conn} do
    conn = post(conn, ~p"/claim", %{"name" => "ShitLord"})

    assert get_session(conn, :registered_name) == "****Lord"
  end

  test "claiming a name someone else registered is refused", %{conn: conn} do
    {:ok, _} = Accounts.register_player("taken")

    conn = post(conn, ~p"/claim", %{"name" => "taken"})

    assert get_session(conn, :registered_name) == nil
    assert Phoenix.Flash.get(conn.assigns.flash, :error) =~ "already claimed"
  end

  test "re-claiming your own name is a friendly no-op", %{conn: conn} do
    conn = post(conn, ~p"/claim", %{"name" => "mine"})
    assert get_session(conn, :registered_name) == "mine"

    conn = post(conn, ~p"/claim", %{"name" => "mine"})
    assert Phoenix.Flash.get(conn.assigns.flash, :info) =~ "already yours"
  end

  test "a blank claim is rejected with a hint", %{conn: conn} do
    conn = post(conn, ~p"/claim", %{"name" => "   "})

    assert get_session(conn, :registered_name) == nil
    assert Phoenix.Flash.get(conn.assigns.flash, :error) =~ "Type a name"
  end

  test "the home page shows the registered badge once claimed", %{conn: conn} do
    conn = post(conn, ~p"/claim", %{"name" => "alice"})
    conn = get(conn, ~p"/")

    assert html_response(conn, 200) =~ "Registered as alice"
  end
end
