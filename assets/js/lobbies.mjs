// Live "open lobbies" list on the home splash (issue #43). Joins the read-only "lobbies"
// channel and renders one row per public room, each with a one-click Join that reuses the
// normal /play/CODE flow through the client router. Returns a teardown that leaves the
// channel and drops the socket, so navigating into a game doesn't leak the connection.
//
// Pure progressive enhancement: with no JS (or if this throws) the #open-lobbies panel
// stays hidden — it has no meaning without the live channel — and players still create or
// join by code exactly as before.

import { Socket } from "phoenix";
import { navigate } from "./router.mjs";

// Wire the home page's open-lobbies panel to the directory channel. No-op (returns nothing)
// if the panel isn't on the page, so it's safe to call from the shared home mount.
export function mountOpenLobbies() {
  const panel = document.getElementById("open-lobbies");
  const list = document.getElementById("open-lobbies-list");
  const count = document.getElementById("open-lobbies-count");
  if (!panel || !list) return;

  const socket = new Socket("/socket", {});
  socket.connect();
  const channel = socket.channel("lobbies", {});
  channel.join();
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
      "dg-btn shrink-0 border border-[var(--dg-magenta)]/40 px-4 py-2 text-xs font-bold uppercase tracking-wide text-pink-100 transition hover:bg-[var(--dg-magenta)]/10 hover:text-white";
    join.textContent = "Join";
    join.addEventListener("click", () => navigate(`/play/${lobby.code}`));

    li.append(info, join);
    return li;
  }

  // Teardown for the router: leave the channel and drop the socket so the home→game hop
  // doesn't leave a dangling directory connection.
  return () => {
    try {
      channel.leave();
    } catch {
      /* already gone */
    }
    try {
      socket.disconnect();
    } catch {
      /* already gone */
    }
  };
}

// "neon" -> "Neon"; a blank/missing theme falls back to a dash so the meta line still reads.
function titleCase(s) {
  if (typeof s !== "string" || !s) return "—";
  return s.charAt(0).toUpperCase() + s.slice(1);
}
