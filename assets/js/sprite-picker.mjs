// The sprite picker on the home splash (#67): the identity card shows your sprite as
// three stacked boxes — hat on top, face in the middle, body on the bottom — each a
// windowed view onto one layer of the default theme's atlas, with arrows cycling that
// layer's options independently. The pick is remembered alongside the name
// (identity.mjs) and rides every join path the same way the name does.
//
// Pure progressive enhancement: with no JS the boxes are empty decoration and the
// arrows do nothing — create/join still work, and the server deals a random look.

import { LOOK_LAYERS, currentLook, rememberLook } from "./identity.mjs";

// The picker previews with the default theme's art — the lobby's actual theme is chosen
// later, by the host. Picks are plain indices, and option N maps onto every theme's
// option N, so the choice made here is the choice rendered in any pack.
const ATLAS_BASE = "/themes/neon";

// Each box is a window onto the pick's 32x32 idle frame at this scale, centred on the
// design-px row where that layer's pixels actually live (hats ride the top of the frame,
// bodies the bottom), so the three stacked boxes read as one cut-up character.
const SCALE = 3;
const CENTER_X = 16.5;
const CENTER_Y = { hat: 9, face: 10, body: 21 };

// One atlas fetch shared across client-side revisits of the splash (#20's router swaps
// the DOM, not the JS VM).
let atlasPromise = null;
const loadAtlas = () => (atlasPromise ??= fetch(`${ATLAS_BASE}/agents.json`).then((r) => r.json()));

// Wire the splash's picker card. No-op when the card isn't on the page; safe to call
// from the shared home mount.
export function mountSpritePicker() {
  const picker = document.getElementById("sprite-picker");
  if (!picker) return;

  loadAtlas()
    .then((atlas) => {
      const options = atlas.meta.layers; // {hat: n, face: n, body: n}

      // The remembered pick, clamped to the live pool (a stale save can outrange a
      // shrunk catalogue) — or a fresh random one. Random, not option 0: the card's
      // preview IS the pick, and defaulting everyone to the same look would make
      // never-customized players recognizable as a cluster of identical sprites.
      const look = currentLook() || randomLook(options);
      for (const layer of LOOK_LAYERS) look[layer] = look[layer] % options[layer];
      rememberLook(look);

      const apply = (layer) => {
        const box = picker.querySelector(`[data-box="${layer}"]`);
        const opt = String(look[layer]).padStart(2, "0");
        const fr = atlas.frames[`${layer}${opt}_idle0`].frame;
        box.style.backgroundImage = `url(${ATLAS_BASE}/agents.png)`;
        box.style.backgroundSize = `${atlas.meta.size.w * SCALE}px ${atlas.meta.size.h * SCALE}px`;
        box.style.backgroundPosition =
          `${box.clientWidth / 2 - (fr.x + CENTER_X) * SCALE}px ` +
          `${box.clientHeight / 2 - (fr.y + CENTER_Y[layer]) * SCALE}px`;
      };
      for (const layer of LOOK_LAYERS) apply(layer);

      // Delegated on the card so one listener serves all six arrows; it lives on DOM
      // the router replaces wholesale on the next swap, so there's nothing to tear down.
      picker.addEventListener("click", (e) => {
        const arrow = e.target.closest("button[data-layer]");
        if (!arrow) return;
        const layer = arrow.dataset.layer;
        const n = options[layer];
        look[layer] = (look[layer] + Number(arrow.dataset.dir) + n) % n;
        rememberLook(look);
        apply(layer);
      });
    })
    .catch(() => {
      /* atlas fetch failed — the boxes stay empty and joins still work (random look) */
    });
}

function randomLook(options) {
  const look = {};
  for (const layer of LOOK_LAYERS) look[layer] = Math.floor(Math.random() * options[layer]);
  return look;
}
