// Your player name as a persistent identity (issue #43 follow-up). The name used to live
// inside the create form and only rode along when you created a lobby; join-by-code mirrored
// it by hand and the one-click public Join dropped it entirely. Now it's a single source of
// truth — one field on the splash, persisted to localStorage — that every join path reads,
// so the name you pick follows you into any lobby you make or join (private or public) and
// survives reloads and return visits.
//
// Progressive enhancement: the field belongs to #create-form via its `form` attribute, so a
// no-JS create still GETs the name through; it just won't be remembered between visits. No-JS
// join-by-code still can't carry the name (the hidden field is mirrored by JS), so that path
// falls back to the room auto-naming you "Player N", exactly as before.

const KEY = "dg:name";
const MAX = 16; // mirrors the field's maxlength and DeadGiveaway.PlayerName.max_length (server-enforced)

// The sprite pick (#67) is the identity's other half: {hat, face, body} option indices,
// chosen in the splash's picker (sprite-picker.mjs) and remembered right alongside the
// name so the look follows the player into any lobby and survives reloads.
const LOOK_KEY = "dg:look";
export const LOOK_LAYERS = ["hat", "face", "body"];

// The name to carry on the next join, or "" for none. Prefers the live field (so a name just
// typed counts immediately) and falls back to the remembered value when the field isn't on
// the page — e.g. a future caller outside the splash.
export function currentName() {
  const el = document.getElementById("player-name");
  const raw = el ? el.value : read();
  return raw.trim().slice(0, MAX);
}

// Append the chosen identity — name and sprite pick (#67) — to a /play/CODE (or /play/new)
// path as query params, or return the path untouched when neither is set. The single place
// URLs get the identity, so create, join and public-join all build it identically (and the
// server validates both again, authoritatively).
export function withIdentity(path) {
  const params = new URLSearchParams();
  const name = currentName();
  if (name) params.set("name", name);
  const look = currentLook();
  if (look) for (const layer of LOOK_LAYERS) params.set(layer, look[layer]);
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

// The remembered sprite pick, or null when none has been made (or storage is blocked).
// Only shape and integer-ness are checked here — the picker clamps indices to the live
// option pool on mount, and the server re-validates on join anyway.
export function currentLook() {
  try {
    const look = JSON.parse(localStorage.getItem(LOOK_KEY));
    return LOOK_LAYERS.every((l) => Number.isInteger(look?.[l]) && look[l] >= 0) ? look : null;
  } catch {
    return null;
  }
}

// Adopt a pick made in the splash's picker as the remembered look.
export function rememberLook(look) {
  try {
    localStorage.setItem(LOOK_KEY, JSON.stringify(look));
  } catch {
    /* storage unavailable — the pick still rides this session's joins */
  }
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

// Adopt a name chosen outside the splash field (the in-lobby rename, #63) as the
// remembered identity, so it follows the player into their next lobby too.
export function rememberName(name) {
  write(name);
}
