// Minimal client-side navigation for the home↔play hop, so the persistent audio shell
// (a JS-module singleton — see audio-shell.mjs) and its live AudioContext survive the move
// instead of being destroyed by a full document reload (#20). We fetch the destination,
// swap the <body> content, and update history — the JS VM (and thus the playing music)
// never tears down.
//
// Pure progressive enhancement: the lobby forms keep their real action/method and the
// in-game links keep their href, so with no JS (or if anything here throws) the app falls
// back to ordinary full-page navigations — the only thing lost is audio seamlessness.

import { LOOK_LAYERS, currentLook, currentName, withIdentity } from "./identity.mjs";

// The active page's teardown (returned by mount()), called before the next swap so the
// outgoing page frees its socket / Pixi app / listeners. null between pages.
let teardown = null;
// The page mounter, injected by app.js (it knows how to boot the game vs the home splash).
// Returns a teardown (or nothing).
let mountFn = async () => {};

/**
 * Wire up client-side navigation and mount the initial, server-rendered page in place.
 * @param {() => (void | (() => void) | Promise<void | (() => void)>)} mount
 */
export async function initRouter(mount) {
  mountFn = mount;

  // Intercept the lobby create/join forms (home page) — submit them in the background and
  // swap to the resulting /play/CODE page without a reload. Delegated on document so it
  // keeps working after each content swap (the forms are replaced, the listener isn't).
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (form.id === "create-form") {
      // GET: append the chosen identity (name + sprite pick, from the identity card) as
      // query params into /play/new. It lives outside this form, so we add it rather
      // than reading it off the form's own fields.
      e.preventDefault();
      navigate(withIdentity(form.action));
    } else if (form.id === "join-form") {
      // POST (carries Phoenix's CSRF token from the form's hidden field). The identity
      // lives in its card — mirror the name and the sprite pick (#67) into the join's
      // hidden fields here, so a guest joining by code carries both in too (this
      // replaced an inline <script>, which wouldn't run after a content swap anyway).
      e.preventDefault();
      const joinName = document.getElementById("join-name");
      if (joinName) joinName.value = currentName();
      const look = currentLook();
      for (const layer of LOOK_LAYERS) {
        const el = document.getElementById(`join-${layer}`);
        if (el) el.value = look ? look[layer] : "";
      }
      navigate(form.action, { method: "POST", body: new FormData(form) });
    }
  });

  // Back/forward: the browser has already updated the URL, so just swap to it (no push).
  window.addEventListener("popstate", () => swap(location.href, { push: false }));

  // Mount the initial, server-rendered page in place (no fetch/swap). A throw here is
  // contained — the page is already rendered; client-nav just won't have a teardown to run.
  try {
    teardown = (await mountFn()) || null;
  } catch {
    teardown = null;
  }
}

/**
 * Client-navigate to `url`. A GET by default; pass {method, body} to submit a form.
 */
export async function navigate(url, { method = "GET", body = null } = {}) {
  await swap(url, { method, body, push: true });
}

async function swap(url, { method = "GET", body = null, push = true } = {}) {
  try {
    const res = await fetch(url, {
      method,
      body,
      credentials: "same-origin",
      // Lets the server distinguish a client-nav fetch from a top-level load if it ever
      // wants to (e.g. skip the layout); harmless today.
      headers: { "x-requested-with": "fetch" },
    });
    const html = await res.text();
    const finalUrl = res.url || url; // fetch followed the redirect; this is /play/CODE (or /)
    const doc = new DOMParser().parseFromString(html, "text/html");

    // Tear the outgoing page down only once we have the new HTML in hand (so a failed
    // fetch above leaves the current page fully intact).
    if (teardown) {
      try {
        teardown();
      } catch {
        /* a half-built page's teardown shouldn't block navigation */
      }
      teardown = null;
    }

    document.title = doc.title;
    document.body.innerHTML = doc.body.innerHTML;
    if (push) window.history.pushState({}, "", finalUrl);
    window.scrollTo(0, 0);

    teardown = (await mountFn()) || null;
  } catch {
    // Network error, parse failure, mount throw — fall back to a real navigation so the
    // user still gets where they're going (just without the seamless audio).
    window.location.assign(url);
  }
}
