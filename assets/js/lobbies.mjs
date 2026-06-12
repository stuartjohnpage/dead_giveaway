// Live "open lobbies" list on the home splash (issue #43). Joins the read-only "lobbies"
// channel and renders one row per public room, each with a one-click Join that reuses the
// normal /play/CODE flow through the client router. Returns a teardown that leaves the
// channel and drops the socket, so navigating into a game doesn't leak the connection.
//
// Pure progressive enhancement: with no JS (or if this throws) the #open-lobbies panel
// stays hidden — it has no meaning without the live channel — and players still create or
// join by code exactly as before.

import { navigate } from "./router.mjs";
import { withIdentity } from "./identity.mjs";
import { openChannel } from "./socket.mjs";

// Wire the home page's open-lobbies panel to the directory channel. No-op (returns nothing)
// if the panel isn't on the page, so it's safe to call from the shared home mount.
export function mountOpenLobbies() {
  const panel = document.getElementById("open-lobbies");
  const list = document.getElementById("open-lobbies-list");
  const count = document.getElementById("open-lobbies-count");
  if (!panel || !list) return;

  const { channel, teardown } = openChannel("lobbies");
  // Surface a failed/timed-out join instead of swallowing it: the panel just stays hidden
  // (its only-show-when-there's-a-game default), and Phoenix auto-rejoins when the socket
  // recovers — re-running the server's after_join push — so the list heals itself; this only
  // makes the failure visible in the console rather than a silent dead panel.
  channel
    .join()
    .receive("error", (reason) => console.warn("lobbies: channel join failed", reason))
    .receive("timeout", () => console.warn("lobbies: channel join timed out"));
  // The server ships the full set on join and on every change (rooms opening, filling,
  // starting, closing), so we just re-render from scratch each time.
  channel.on("lobbies", (payload) => render(payload.lobbies || []));

  function render(lobbies) {
    list.replaceChildren(...lobbies.map(rowEl));
    // Only show the panel when there's actually a game to drop into — an empty box on
    // every visit would just be clutter.
    panel.hidden = lobbies.length === 0;
    if (count) count.textContent = lobbies.length ? String(lobbies.length) : "";
  }

  // One row: host + a meta line (theme · player count · status) on the left, a Join
  // button on the right. Built with textContent (never innerHTML) so a host's name —
  // player-supplied text, even if profanity-redacted server-side — can't inject markup.
  function rowEl(lobby) {
    const li = document.createElement("li");
    li.className =
      "flex items-center justify-between gap-3 border border-white/10 bg-[var(--dg-ink)]/60 px-3 py-2";

    const info = document.createElement("div");
    info.className = "min-w-0";

    const host = document.createElement("p");
    host.className = "truncate font-semibold text-white";
    host.textContent = lobby.host || `Lobby ${lobby.code}`;

    const meta = document.createElement("p");
    meta.className =
      "mt-0.5 truncate font-mono text-[0.6rem] uppercase tracking-[0.15em] text-slate-400";
    const players = `${lobby.players} ${lobby.players === 1 ? "player" : "players"}`;
    const status = lobby.in_progress ? "in progress" : "waiting";
    meta.textContent = `${titleCase(lobby.theme)} · ${players} · ${status}`;

    info.append(host, meta);

    const join = document.createElement("button");
    join.type = "button";
    join.className =
      "dg-btn shrink-0 border border-cyan-400/40 px-4 py-2 text-xs font-bold uppercase tracking-wide text-cyan-200 transition hover:bg-cyan-400/10 hover:text-white";
    join.textContent = "Join";
    // Carry the player's chosen identity in (withIdentity appends name + sprite pick),
    // so a one-click public join arrives identified just like create / join-by-code.
    join.addEventListener("click", () => navigate(withIdentity(`/play/${lobby.code}`)));

    li.append(info, join);
    return li;
  }

  // Teardown for the router: leave the channel and drop the socket so the home→game hop
  // doesn't leave a dangling directory connection.
  return teardown;
}

// "neon" -> "Neon"; a blank/missing theme falls back to a dash so the meta line still reads.
function titleCase(s) {
  if (typeof s !== "string" || !s) return "—";
  return s.charAt(0).toUpperCase() + s.slice(1);
}
