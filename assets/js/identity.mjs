// Your player name as a persistent identity (issue #43 follow-up). The name used to live
// inside the create form and only rode along when you created a lobby; join-by-code mirrored
// it by hand and the one-click public Join dropped it entirely. Now it's a single source of
// truth — one field on the splash, persisted to localStorage — that every join path reads,
// so the name you pick follows you into any lobby you make or join (private or public) and
// survives reloads and return visits.
//
// Progressive enhancement: with no JS the field still posts/gets as before; it just won't be
// remembered between visits, and the room auto-names you "Player N" (the same fallback that
// already applied to join-by-code without JS).

const KEY = "dg:name";
const MAX = 16; // matches the input's maxlength and the server's String.slice/3 cap

// The name to carry on the next join, or "" for none. Prefers the live field (so a name just
// typed counts immediately) and falls back to the remembered value when the field isn't on
// the page — e.g. a future caller outside the splash.
export function currentName() {
  const el = document.getElementById("player-name");
  const raw = el ? el.value : read();
  return raw.trim().slice(0, MAX);
}

// Append the chosen name to a /play/CODE (or /play/new) path as a query param, or return the
// path untouched when no name is set. The single place URLs get the name, so create, join and
// public-join all build it identically (and the server trims/caps it again, authoritatively).
export function withName(path) {
  const name = currentName();
  return name ? `${path}?name=${encodeURIComponent(name)}` : path;
}

// Hydrate the splash's name field from the remembered value and keep the two in sync as the
// user types. Safe to call on any page: a no-op when the field isn't present. No teardown —
// the listener lives on DOM the router replaces wholesale on the next swap.
export function mountIdentity() {
  const el = document.getElementById("player-name");
  if (!el) return;
  // Don't clobber a value the browser may have already restored on the field.
  if (!el.value) {
    const saved = read();
    if (saved) el.value = saved;
  }
  el.addEventListener("input", () => write(el.value));
}

// localStorage can throw (private mode, blocked storage) — never let a remembered-name nicety
// break the splash, so both sides swallow failures and degrade to "not remembered".
function read() {
  try {
    return localStorage.getItem(KEY) || "";
  } catch {
    return "";
  }
}

function write(value) {
  try {
    localStorage.setItem(KEY, value.trim().slice(0, MAX));
  } catch {
    /* storage unavailable — the in-page field still works for this session */
  }
}
