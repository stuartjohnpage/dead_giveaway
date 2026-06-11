// Dead Giveaway browser client (DESIGN §9): connects the websocket, joins a room,
// and renders the authoritative snapshots with Pixi. Pure math lives in
// coords.mjs (unit-tested); this module is the Pixi + socket + input glue.

import { Application, AnimatedSprite, Assets, Container, Graphics, Rectangle, Sprite, Texture, TilingSprite } from "pixi.js";
import { openChannel } from "./socket.mjs";
import { worldToScreen, screenToWorld } from "./coords.mjs";
import { advance, reconcile } from "./prediction.mjs";
import {
  getAudio,
  DEFAULT_MENU_LOOP,
  DEFAULT_GAME_STAGES,
  DEFAULT_SHOT,
  DEFAULT_WINDUP,
} from "./audio-shell.mjs";
import { navigate } from "./router.mjs";
import { rememberName } from "./identity.mjs";

const PAD = 24;
const ROW_SPACING = 10; // must match DeadGiveaway.World @row_spacing

// The theme art is authored at a fixed 1280×720 (the backgrounds' native size). We
// render the whole scene at that "design resolution" and letterbox-scale it to the
// window, so sprites keep their pixel proportions and arena_bg lines up 1:1.
const DESIGN_W = 1280;
const DESIGN_H = 720;
// The floor band sits inside arena_bg's top/bottom neon rails (its "walls").
const FLOOR_TOP = 64;
const FLOOR_H = DESIGN_H - 2 * FLOOR_TOP;

// Theme asset packs live one-folder-each under /themes/<key>/ (art + audio + bullet +
// theme.json manifest); see priv/static/themes/README.md. The room's theme is host-set
// in the lobby and broadcast, so the whole look/sound is swapped at runtime by
// loadTheme() below — no hardcoded key. Cosmetic variants are NOT tied to the human/bot
// mapping (DESIGN §4, §9).
const DEFAULT_THEME = "neon";
const themeBase = (key) => `/themes/${key}`;
// The default theme's audio tracks (the fallback when a pack omits its own) live with the
// rest of the audio in audio-shell.mjs; loadTheme imports them for that fallback.
// Default cosmetic-variant count; a theme's manifest can override it.
const VARIANTS = 12;
const SPRITE_SCALE = 1.5; // 32px art → 48px on the field
// Lanes are confined to the floor band, inset by the sprite's half-height so the
// top/bottom runners sit inside the neon rails rather than straddling them.
const LANE_PAD_Y = FLOOR_TOP + SPRITE_SCALE * 16;
// Per-state animation cadence (frames/tick); see the theme README.
const ANIM_SPEED = { idle: 0.05, walk: 0.15, run: 0.28, dropped: 0 };
// The snapshot's verb (plus the alive flag) is all we need to pick an animation —
// the server already ships it (world.ex), so animation needs no protocol change.
const stateFor = (e) =>
  !e.alive ? "dropped" : e.verb === "run" ? "run" : e.verb === "walk" ? "walk" : "idle";

export async function boot() {
  const mount = document.getElementById("game");
  if (!mount) return;

  const room = mount.dataset.room;
  // `data-host` (set server-side from the creator's session, not the URL) only asks
  // the server to *create* this room; a join-by-code requires it to already exist (the server replies "not_found"
  // otherwise). It does NOT grant host privileges — the server assigns those to the
  // first player in and tells us via the lobby roster, so a crafted URL can't steal them.
  const wantsCreate = mount.dataset.host === "true";
  // Whether *we* host (enable the config knobs, close the lobby on leave). Server-set:
  // false until the first lobby roster names the host, then kept current as it changes.
  let isHost = false;
  // The name the player chose on the splash (empty → the room auto-names us).
  const playerName = mount.dataset.name || "";

  const app = new Application();
  // The canvas tracks the window; the world container (below) is letterbox-scaled to
  // fit it. antialias off + nearest-neighbour scaling keeps the pixel art crisp.
  // Render at the device pixel ratio (autoDensity sizes the canvas in CSS pixels while
  // backing it at native resolution) so the scene is sharp on HiDPI/retina screens
  // instead of upscaled and soft (#24). app.screen stays in CSS pixels, so the letterbox
  // math and the mouse→world mapping are unaffected.
  await app.init({
    resizeTo: window,
    background: "#0b1020",
    antialias: false,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  });
  mount.appendChild(app.canvas);

  // The sprite atlas (cosmetic variants × idle/walk/run/dropped) and backdrop art are
  // loaded by loadTheme() rather than once up front, so a lobby theme switch can swap
  // them at runtime. `sheet` and `variants` are reassigned there; the scene objects
  // below are built once with empty textures and have their textures swapped in.
  let sheet = null;
  let variants = VARIANTS;

  // World-space scene graph, all under one container we scale to fit the window.
  // Layers back→front: arena backdrop, tiled floor band, finish line, runners. The
  // backdrop/floor/finish textures (and their texture-derived sizing) are set in loadTheme.
  const world = new Container();
  app.stage.addChild(world);

  const arena = new Sprite(Texture.EMPTY);
  world.addChild(arena);

  const floor = new TilingSprite({ texture: Texture.EMPTY, width: DESIGN_W, height: FLOOR_H });
  floor.y = FLOOR_TOP;
  world.addChild(floor);

  // worldW always equals finish_x, so the finish maps to the right margin regardless
  // of the configured value — its screen position is fixed. Every pack paints its line
  // along the texture's LEFT edge, so anchoring that edge on the logical line puts the
  // paint exactly where the win fires (#56); loadTheme crops the art so the checker
  // sliver past the line ends flush with the arena instead of spilling off it.
  const finish = new Sprite(Texture.EMPTY);
  finish.anchor.set(0, 0);
  finish.x = DESIGN_W - PAD;
  finish.y = FLOOR_TOP;
  world.addChild(finish);

  const entityLayer = new Container();
  world.addChild(entityLayer);

  // The wind-up telegraph (#60): the watcher's spin alone wasn't reading — players'
  // eyes are on their own runner, not the line — so the whole arena carries the
  // warning. A rim around the field pulses amber through the wind-up ("about to
  // turn"), then holds red while the light is red: dropping it at the exact moment
  // moving becomes lethal would read as the all-clear. Gone on green and in classic.
  const RIM_W = 10;
  const RIM_WINDUP = 0xffb020;
  const RIM_RED = 0xff2d3f;
  const lightRim = new Graphics()
    .rect(0, 0, DESIGN_W, RIM_W)
    .rect(0, DESIGN_H - RIM_W, DESIGN_W, RIM_W)
    .rect(0, RIM_W, RIM_W, DESIGN_H - 2 * RIM_W)
    .rect(DESIGN_W - RIM_W, RIM_W, RIM_W, DESIGN_H - 2 * RIM_W)
    .fill(0xffffff); // white base — the live colour comes from tint per light state
  lightRim.visible = false;
  world.addChild(lightRim);

  // The Red Light watcher (#53): the landmark on the finish line, present only while
  // snapshots carry a `light`. Its pose tracks the room-global light — facing away
  // (green), spinning (wind-up), facing the crowd (red) — and the wind-up cue makes
  // the warning audible without staring at the line. All enforcement is server-side;
  // this is pure presentation. The atlas is per-theme (loadTheme below); the sprite
  // is built lazily once a sheet exists and dropped on a theme swap like the agents.
  let watcherSheet = null;
  let watcher = null;
  let light = null; // the last snapshot's light — null through a classic round
  const WATCHER_SCALE = 2; // 48px art → 96px on the field: bigger than any agent
  const WATCHER_ANIM = { green: "idle", windup: "spin", red: "watch" };
  const WATCHER_SPEED = { idle: 0.05, spin: 0.3, watch: 0.08 };

  const ensureWatcher = () => {
    if (watcher || !watcherSheet) return;
    watcher = new AnimatedSprite(watcherSheet.animations.idle);
    watcher.anchor.set(0.5);
    watcher.scale.set(WATCHER_SCALE);
    // On the line, mid-field, drawn over the runners passing it — a landmark, nudged
    // left so it doesn't spill past the design edge. Placement tuned by feel.
    watcher.x = finish.x - 30;
    watcher.y = DESIGN_H / 2;
    watcher.visible = false;
    watcher.play();
    world.addChild(watcher);
  };

  const setLight = (next) => {
    if (next === light) return;
    light = next;
    // The spin is the warning (#53) — make it heard even off-screen-focus.
    if (next === "windup") playWindup();
    lightRim.visible = next === "windup" || next === "red";
    lightRim.tint = next === "red" ? RIM_RED : RIM_WINDUP;
    lightRim.alpha = next === "red" ? 0.9 : 1; // wind-up alpha is pulsed by the ticker
    ensureWatcher();
    if (!watcher) return; // no watcher art anywhere — the light still enforces server-side
    watcher.visible = !!next;
    const frames = next && watcherSheet.animations[WATCHER_ANIM[next]];
    if (frames) {
      watcher.textures = frames;
      watcher.animationSpeed = WATCHER_SPEED[WATCHER_ANIM[next]];
      watcher.play();
    }
  };

  // Cheap integer hash so id→variant looks scattered rather than a row-by-row cycle,
  // while staying deterministic (same id → same look for every client) and
  // independent of the human/bot mapping, so the sprite never hints at who is human.
  const variantFor = (id) =>
    String((Math.imul(id ^ 0x9e3779b9, 0x85ebca6b) >>> 0) % variants).padStart(2, "0");

  const sprites = new Map(); // entity id -> { sprite, tx, ty, state, variant }
  // The view is the fixed design resolution; the letterbox scale maps it to the
  // window, so coords.mjs always works in 1280×720 regardless of canvas size.
  const view = { worldW: 1000, worldH: 50, screenW: DESIGN_W, screenH: DESIGN_H, padX: PAD, padY: LANE_PAD_Y };

  // Letterbox: scale the world to fit the window and centre it within the canvas.
  const layout = () => {
    const s = Math.min(app.screen.width / DESIGN_W, app.screen.height / DESIGN_H);
    world.scale.set(s);
    world.x = (app.screen.width - DESIGN_W * s) / 2;
    world.y = (app.screen.height - DESIGN_H * s) / 2;
  };
  layout();
  window.addEventListener("resize", layout);

  // Crosshair lives in screen space so it tracks the raw mouse with no transform. Its
  // texture — the pack's crosshair sprite, or a drawn cross tinted to the theme's
  // accent when the pack has none — is set in loadTheme.
  const myCross = new Sprite(Texture.EMPTY);
  myCross.anchor.set(0.5);
  app.stage.addChild(myCross);

  // The pink reticle *is* your pointer while you're armed, so hide the OS cursor over
  // the canvas whenever it's up — no arrow sitting on top of the crosshair. When the
  // reticle is gone (lobby, between rounds, or after your last shot) the real cursor
  // comes back so you can still click the canvas / read the field. The lobby overlay
  // sits above the canvas with its own default cursor, so its buttons stay normal.
  const setCrosshairVisible = (v) => {
    myCross.visible = v;
    app.canvas.style.cursor = v ? "none" : "default";
  };
  setCrosshairVisible(false); // boot into the lobby: no reticle, normal cursor

  // Everyone sees every crosshair (DESIGN §5): peers' reticles arrive (anonymised) on
  // the snapshot stream as a bare list of world points. We pool one sprite per point
  // and interpolate it toward its latest position, exactly like the body sprites, so
  // the reticles glide rather than step at the 20Hz snapshot rate. They share myCross's
  // texture — all reticles look identical, which is *why* you find your own by moving
  // the mouse (DESIGN §5). Like myCross they live in screen space (added to the stage),
  // so they stay the same on-screen size as your own regardless of the letterbox scale.
  const peerCrosses = []; // pool of { sprite, cwx, cwy, twx, twy, live }
  const clearPeerCrosses = () => {
    for (const pc of peerCrosses) {
      pc.sprite.visible = false;
      pc.live = false; // next time this slot is used it snaps in, not flies from a stale spot
    }
  };

  // All audio — the two background loops, the music director that drives them (which loop,
  // when to replay, the autoplay unlock, boot-load vs live theme swap), the firing SFX and
  // the shared volume level — lives in the persistent audio shell (audio-shell.mjs), so it
  // can outlive any single boot() once navigation is client-side (#20). The volume is
  // configured on the home page and read fresh per transition. Arm the director's autoplay
  // unlock: the menu loop is queued, awaiting the first user gesture to sound.
  const { music, playShot, setShotUrl, playWindup, setWindupUrl, armUnlock, lobbyMusic } =
    getAudio();
  armUnlock();

  // --- Lobby overlay (the default view; hidden only while a round runs) ---
  // These all ship together in game_html/show.html.heex, so we resolve them
  // once and trust they're present rather than nil-guarding every use.
  const lobby = document.getElementById("lobby");
  const lobbyScrim = document.getElementById("lobby-scrim");
  const lobbyBanner = document.getElementById("lobby-banner");
  const lobbyCode = document.getElementById("lobby-code");
  const lobbyList = document.getElementById("lobby-list");
  const lobbyHint = document.getElementById("lobby-hint");
  const lobbyBack = document.getElementById("lobby-back");
  const lobbyLeave = document.getElementById("lobby-leave");
  const goButton = document.getElementById("go");
  const modeSelect = document.getElementById("mode-select");
  const setupSelect = document.getElementById("setup-select");
  const ammoSelect = document.getElementById("ammo-select");
  const chancesSelect = document.getElementById("chances-select");
  const themeSelect = document.getElementById("theme-select");
  const paceSelect = document.getElementById("pace-select");
  const visibilitySelect = document.getElementById("visibility-select");

  // Bullets-per-round is the host's call: guests see a disabled select reflecting the
  // host's choice (kept current by the lobby broadcast). The host's changes push to the
  // room, which clamps and re-broadcasts the value to everyone. The disabled state is
  // driven by applyHostUI (below), since who hosts can change.
  ammoSelect.addEventListener("change", () => {
    channel.push("set_config", { max_ammo: Number(ammoSelect.value) });
  });
  // Mirror a numeric host knob from a lobby broadcast into our local copy (via `set`)
  // and the disabled-for-guests <select>, ignoring anything non-numeric.
  const applyNumericConfig = (n, set, select) => {
    if (typeof n !== "number") return;
    set(n);
    select.value = String(n);
  };
  // Reflect the bullet count (and our local maxAmmo) from a broadcast.
  const applyMaxAmmo = (n) => applyNumericConfig(n, (v) => (maxAmmo = v), ammoSelect);

  // Lives-per-round is the other numeric host knob (same shape as the bullet count):
  // 1 = "shot = out", above 1 a dropped player takes over a free bot body (DESIGN §7).
  chancesSelect.addEventListener("change", () => {
    channel.push("set_config", { max_chances: Number(chancesSelect.value) });
  });
  // Reflect the life count (and our local maxChances) from a broadcast, so guests track
  // the host's pick and the HUD knows whether to appear.
  const applyMaxChances = (n) => applyNumericConfig(n, (v) => (maxChances = v), chancesSelect);

  // The theme is the other host-set knob (same shape as the bullet count): a guest's
  // select is disabled and just reflects the host's pick. Pushing it lets the room
  // validate + broadcast, so every client's loadTheme runs off the same value.
  themeSelect.addEventListener("change", () => {
    channel.push("set_config", { theme: themeSelect.value });
  });
  // Mirror the room's theme from a broadcast: reflect it in the control and (re)load the
  // pack. loadTheme no-ops when the theme is already current, so the recurring lobby
  // broadcasts don't reload; a real change swaps art/audio for this client.
  const applyTheme = (key) => {
    if (typeof key !== "string" || !key) return;
    themeSelect.value = key;
    loadTheme(key);
  };

  // Pace (#17): the round-tempo knob, same host-only shape as the others. A guest's select
  // is disabled and just reflects the host's pick; pushing it lets the room validate +
  // broadcast so every lobby shows the same value. It only affects the next round's bots.
  paceSelect.addEventListener("change", () => {
    channel.push("set_config", { pace: paceSelect.value });
  });
  const applyPace = (pace) => {
    if (typeof pace === "string" && pace) paceSelect.value = pace;
  };

  // Public/private visibility (issue #43), same host-only shape as the other knobs. The
  // <select> carries "public"/"private"; we push a boolean the room validates + broadcasts
  // so every lobby (and the home directory) reflects the host's choice.
  visibilitySelect.addEventListener("change", () => {
    channel.push("set_config", { public: visibilitySelect.value === "public" });
  });
  const applyVisibility = (pub) => {
    if (typeof pub === "boolean") visibilitySelect.value = pub ? "public" : "private";
  };

  // Game mode (#53): Classic, or Red Light / Green Light with the watcher on the
  // finish line. A real room knob with the standard host-only shape: the room
  // validates ("classic"/"red_light") and broadcasts, so every client tracks it.
  modeSelect.addEventListener("change", () => {
    channel.push("set_config", { mode: modeSelect.value });
  });
  const applyGameMode = (mode) => {
    if (typeof mode === "string" && mode) modeSelect.value = mode;
  };

  // Setup preset (Standard/Custom) is a host-side UI convenience, not a room knob: the
  // actual ruleset still travels as the bullets/lives/pace config. "Standard" is the
  // preset (1 bullet, 1 life, fast) and hides those three rows; "Custom" reveals them.
  const STANDARD = { ammo: 1, chances: 1, pace: "fast" };
  const customRows = document.querySelectorAll(".dg-custom-option");
  // True when the current bullets/lives/pace all sit at the standard preset — i.e. there's
  // nothing a Custom view would add. Read off the selects (kept current by the broadcast).
  const atStandardPreset = () =>
    Number(ammoSelect.value) === STANDARD.ammo &&
    Number(chancesSelect.value) === STANDARD.chances &&
    paceSelect.value === STANDARD.pace;
  // Show the bullets/lives/pace rows only in Custom setup. The host drives this from the
  // Setup select; guests have no say, so we infer their setup from the broadcast values
  // (if they're all at the preset there's nothing extra to show) and reflect it in their
  // disabled Setup select for consistency with the other host-only knobs.
  const applySetup = () => {
    const custom = isHost ? setupSelect.value === "custom" : !atStandardPreset();
    if (!isHost) setupSelect.value = custom ? "custom" : "standard";
    customRows.forEach((el) => el.classList.toggle("hidden", !custom));
  };
  // Switching to Standard snaps the per-round knobs back to the preset and pushes each to
  // the room so guests follow; setting the values first keeps our own view in sync and
  // makes atStandardPreset agree. Custom just reveals the rows with their current values.
  setupSelect.addEventListener("change", () => {
    if (setupSelect.value === "standard") {
      ammoSelect.value = String(STANDARD.ammo);
      chancesSelect.value = String(STANDARD.chances);
      paceSelect.value = STANDARD.pace;
      maxAmmo = STANDARD.ammo;
      maxChances = STANDARD.chances;
      channel.push("set_config", { max_ammo: STANDARD.ammo });
      channel.push("set_config", { max_chances: STANDARD.chances });
      channel.push("set_config", { pace: STANDARD.pace });
    }
    applySetup();
  });

  // --- In-round ammo HUD: your bullets for the round (DESIGN §5) ---
  const hudAmmo = document.getElementById("hud-ammo");
  const ammoBullet = document.getElementById("ammo-bullet");
  const ammoCount = document.getElementById("ammo-count");
  // Bullets the host grants per round (from the lobby broadcast) and how many of those
  // are still in hand this round. A fresh round reloads `ammo` back up to `maxAmmo`.
  let maxAmmo = 1;
  let ammo = 1;
  // Whether the local player's body has been dropped this round (a private "out" from
  // the room, #11). Crosshairs are anonymous, so the client can't tell which body is
  // its own and can't infer its own death from the snapshot — the room signals it
  // directly. While dead we hide our reticle and ignore fire/aim (we're spectating, §7).
  let dead = false;
  // Client-side prediction of our own body (#41): the room privately tells us which
  // entity id we drive (a "you" push at round start, re-pointed on a bot takeover §7) —
  // the one self-id carve-out in DESIGN §9. We apply our own verb to that body the
  // instant a key changes and reconcile against each snapshot, so movement responds
  // this frame instead of a tick-plus-latency later. Only how the body's *motion is
  // sourced* changes: it renders identically to every other body — same sprite, no
  // highlight — so the find-yourself opening is untouched (DESIGN §2).
  let myBodyId = null; // our body's entity id, or null when we don't drive one
  let predictedX = null; // its predicted world x; null until a snapshot seeds it
  // Reflect the remaining count: show the number, and once it hits 0 drop the bullet icon.
  const setAmmo = (n) => {
    ammoCount.textContent = String(n);
    ammoBullet.hidden = n <= 0;
  };
  // The HUD only belongs on screen during a live round, not the lobby or the card.
  // Showing it (re)loads a full clip for the round just starting.
  const showAmmo = (visible) => {
    if (visible) {
      ammo = maxAmmo;
      setAmmo(ammo);
    }
    hudAmmo.hidden = !visible;
  };

  // --- In-round lives HUD: your remaining lives this round (DESIGN §7) ---
  const hudChances = document.getElementById("hud-chances");
  const chancesCount = document.getElementById("chances-count");
  // Lives the host grants per round (from the lobby broadcast) and how many remain. The
  // room owns the truth and pushes a private "chances" update on every change (round
  // start, and each bot takeover); we just reflect it. Single-life rounds hide the HUD
  // entirely — there dying is simply "out", with nothing to count.
  let maxChances = 1;
  const setChances = (n) => {
    chancesCount.textContent = String(n);
  };
  const showChances = (visible) => {
    // Only meaningful when more than one life is in play; otherwise stay hidden.
    hudChances.hidden = !(visible && maxChances > 1);
  };

  // Backing out is destructive for the host (it closes the lobby for everyone); the
  // label (set by applyHostUI) says so, while a guest only leaves their own seat.
  lobbyLeave.addEventListener("click", () => {
    channel.push("leave", {});
    // Client-navigate home so the menu music carries straight back (#20); the router runs
    // boot()'s teardown (below), which leaves the channel and tears the canvas/socket down.
    navigate("/");
  });

  // Reflect our server-assigned host status in the lobby controls: only the host can
  // change the bullet count / theme or close the whole lobby. Re-run from the lobby
  // roster whenever the host changes (e.g. the old host left and the room handed off).
  const applyHostUI = () => {
    modeSelect.disabled = !isHost;
    setupSelect.disabled = !isHost;
    ammoSelect.disabled = !isHost;
    chancesSelect.disabled = !isHost;
    themeSelect.disabled = !isHost;
    paceSelect.disabled = !isHost;
    visibilitySelect.disabled = !isHost;
    // Host status flips how the setup is derived (own Setup select vs. inferred from values).
    applySetup();
    // Only the host starts the round (the server enforces this too); a guest's Go is
    // disabled and a hint tells them they're waiting on the lobby leader. Skip the hint
    // while a round is starting ("starting…") so we don't stomp that transient message.
    goButton.disabled = !isHost;
    if (!isHost && lobbyHint.textContent !== "starting…") {
      lobbyHint.textContent = "Waiting for the host to start…";
    }
    lobbyLeave.textContent = isHost ? "Close lobby" : "Leave lobby";
    // The host's close is destructive (it ends the lobby for everyone), so make it
    // read dark red; a guest only leaves their own seat, so it stays neutral slate.
    lobbyLeave.classList.toggle("bg-red-800", isHost);
    lobbyLeave.classList.toggle("hover:bg-red-700", isHost);
    lobbyLeave.classList.toggle("bg-slate-700", !isHost);
    lobbyLeave.classList.toggle("hover:bg-slate-600", !isHost);
  };
  applyHostUI();

  // Show the shareable code so the host can pass it to friends.
  lobbyCode.textContent = `Code: ${room}`;

  let myName = "";
  let banner = "Lobby";
  let roster = [];
  let scores = null; // set after a round; shown until the next round starts

  const renderLobby = () => {
    lobbyBanner.textContent = banner;
    goButton.textContent = scores ? "Play again" : "Go";
    lobbyList.innerHTML = "";
    const rows = scores
      ? Object.entries(scores)
          .sort((a, b) => b[1] - a[1])
          .map(([n, w]) => [n, `: ${w}`])
      : roster.map((n) => [n, ""]);
    for (const [n, suffix] of rows) {
      const li = document.createElement("li");
      li.textContent = (n === myName ? `${n} (you)` : n) + suffix;
      // Your own roster row carries the rename control (#63) — lobby roster only;
      // the post-round standings and the round itself pin names.
      if (!scores && n === myName) li.appendChild(renameButton(li));
      lobbyList.appendChild(li);
    }
  };

  // The in-lobby rename (#63): swap my roster row for an input; Enter (or leaving the
  // field) pushes the new name, and the reply's canonical form — trimmed, redacted and
  // uniquified by the same path a join takes — becomes my identity everywhere (the
  // refreshed roster reaches the rest of the lobby via the lobby broadcast).
  const renameButton = (li) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "✎";
    btn.title = "Change name";
    btn.className = "ml-2 align-middle font-mono text-xs text-cyan-300/80 hover:text-cyan-200";
    btn.addEventListener("click", () => {
      const input = document.createElement("input");
      input.type = "text";
      input.maxLength = 16; // mirrors the splash field and the server's length cap
      input.value = myName;
      input.className =
        "w-36 border border-cyan-400/30 bg-transparent px-1 text-sm text-white outline-none";
      li.replaceChildren(input);
      input.focus();
      input.select();
      let done = false; // Enter also blurs the input — submit only once
      const submit = () => {
        if (done) return;
        done = true;
        const next = input.value.trim();
        if (!next || next === myName) return renderLobby(); // unchanged → restore the row
        channel.push("rename", { name: next }).receive("ok", (resp) => {
          if (resp && resp.name) {
            myName = resp.name;
            rememberName(myName); // follow the player into their next lobby too
          }
          renderLobby(); // don't wait on the lobby broadcast to un-stick the row
        });
      };
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") submit();
        else if (ev.key === "Escape") {
          done = true;
          renderLobby();
        }
      });
      input.addEventListener("blur", submit);
    });
    return btn;
  };
  // The themed lobby backdrop (a CSS url(...), set by loadTheme) and whether the full
  // lobby is currently showing it. The post-round overlay card hides it (the frozen
  // game shows through); loadTheme consults `lobbyShowingFull` to know whether to apply
  // a freshly-loaded backdrop immediately or just stash it for the next full lobby.
  let lobbyBg = "none";
  let lobbyShowingFull = false;

  // Reveal the lobby card. `overlay` true floats it over the (now-frozen) game — the
  // post-round "Play again?" card, so the player stays in the game rather than being
  // kicked back to a full-screen lobby. `overlay` false is the pre-game lobby: the
  // full themed backdrop and its scrim. Music is driven by the channel handlers, not
  // here, since this is also called redundantly (every snapshot calls hideCard).
  const showCard = (overlay) => {
    renderLobby();
    // Reset the start control to its resting state, then let applyHostUI re-gate it:
    // the host gets an enabled Go/Play-again, a guest a disabled button + waiting hint.
    goButton.disabled = false;
    lobbyHint.textContent = "";
    applyHostUI();
    lobbyScrim.style.display = overlay ? "none" : "";
    lobbyShowingFull = !overlay;
    // Overlay: transparent so the frozen game shows behind the card. Full lobby: the
    // class's solid bg colour plus the themed backdrop image.
    lobby.style.backgroundColor = overlay ? "transparent" : "";
    lobby.style.backgroundImage = overlay ? "none" : lobbyBg;
    lobby.style.display = "flex";
  };
  const hideCard = () => {
    lobby.style.display = "none";
  };

  // Load (or swap to) a theme pack: fetch its manifest, then point the scene's textures,
  // the atlas, the reticle, the ammo icon, the lobby backdrop and both music loops at the
  // pack's assets. Called once at boot for the default theme and again whenever the
  // lobby's theme broadcast changes (host's pick). A no-op if the theme is already loaded.
  // Safe to run mid-session because the server only lets the theme change while no round
  // is live, so there are no entities mid-flight when the atlas swaps.
  let currentTheme = null;
  async function loadTheme(key) {
    if (key === currentTheme) return;
    const base = themeBase(key);
    const url = (f) => `${base}/${f}`;

    let manifest;
    try {
      manifest = await (await fetch(`${base}/theme.json`)).json();
    } catch {
      return; // missing/broken manifest — keep the current look rather than blanking out
    }
    const a = manifest.assets || {};

    // Atlas + backdrop textures (nearest-neighbour to keep the pixel art crisp).
    const newSheet = await Assets.load(url(a.agentsAtlas));
    for (const tex of Object.values(newSheet.textures)) tex.source.scaleMode = "nearest";
    const [arenaTex, finishTex, floorTex] = await Promise.all(
      [a.arenaBackground, a.finishLine, a.floorTile].map((f) => Assets.load(url(f))),
    );
    for (const t of [arenaTex, finishTex, floorTex]) t.source.scaleMode = "nearest";

    // Swap textures on the existing scene objects. Sprite width/height derive from the
    // texture, so (re)set them after assigning; the TilingSprite keeps its own size.
    arena.texture = arenaTex;
    arena.width = DESIGN_W;
    arena.height = DESIGN_H;
    floor.texture = floorTex;
    // Only PAD design px fit between the logical line and the arena's right edge, so
    // crop the finish art to that slice — the painted line plus a checker sliver (#56).
    finish.texture = new Texture({
      source: finishTex.source,
      frame: new Rectangle(0, 0, PAD, finishTex.height),
    });
    finish.height = FLOOR_H;
    sheet = newSheet;
    variants = manifest.variants || VARIANTS;

    // The old atlas's entity sprites are now stale — drop them so the next snapshot
    // rebuilds from the new atlas. (No round is live during a theme change.)
    for (const [id, s] of sprites) {
      entityLayer.removeChild(s.sprite);
      s.sprite.destroy();
      sprites.delete(id);
    }

    // The Red Light watcher's atlas (#53): the pack's own, or the default theme's when
    // this pack hasn't shipped one (the gameStages fallback rule). With neither, red
    // light rounds simply run watcher-less on this client — the server still enforces.
    const watcherAtlas = a.watcher ? url(a.watcher) : `${themeBase(DEFAULT_THEME)}/watcher.json`;
    try {
      watcherSheet = await Assets.load(watcherAtlas);
      for (const tex of Object.values(watcherSheet.textures)) tex.source.scaleMode = "nearest";
    } catch {
      watcherSheet = null;
    }
    // Like the agents, the built sprite is stale on a swap — rebuilt lazily by setLight.
    if (watcher) {
      world.removeChild(watcher);
      watcher.destroy();
      watcher = null;
    }

    const ui = manifest.ui || {};

    // Reticle (#48): the pack's crosshair sprite when it ships one; a drawn cross
    // tinted to ui.reticle otherwise (also the fallback for a broken sprite path).
    // Peers' reticles adopt myCross.texture per snapshot, so they follow the theme
    // automatically. Cosmetic only — size and centered anchor stay consistent across
    // themes, so aim feel never changes (DESIGN §9). Swapped-out textures are never
    // destroyed: pack sprites belong to the shared Assets cache, and a stray drawn
    // cross is a ~38px texture on a rare lobby event — not worth tracking ownership.
    let newCross = null;
    if (ui.crosshair) {
      try {
        newCross = await Assets.load(url(ui.crosshair));
        newCross.source.scaleMode = "nearest";
      } catch {
        newCross = null; // manifest points at a missing file — fall back to the drawn cross
      }
    }
    if (!newCross) {
      const reticle = ui.reticle || "#ff5577";
      newCross = app.renderer.generateTexture(
        new Graphics()
          .circle(0, 0, 11)
          .stroke({ width: 2, color: reticle })
          .moveTo(-15, 0)
          .lineTo(15, 0)
          .moveTo(0, -15)
          .lineTo(0, 15)
          .stroke({ width: 2, color: reticle }),
      );
    }
    myCross.texture = newCross;

    // Ammo HUD icon (the theme's bullet).
    if (ui.bullet) ammoBullet.src = url(ui.bullet);

    // Lobby backdrop: stash the themed image; apply it now only if the full lobby is up
    // (the overlay card stays transparent so the game shows through).
    if (a.lobbyBackground) {
      lobbyBg = `url(${url(a.lobbyBackground)})`;
      if (lobbyShowingFull) lobby.style.backgroundImage = lobbyBg;
    }

    // Music: lobby loop + escalating game stages, falling back to the default theme's
    // tracks if this pack hasn't declared (or generated) its own yet. The director points
    // both loops at the new tracks and decides boot-load (no replay; first playback is the
    // toLobby() below) vs live-swap (restart whatever's playing) off its own first-load flag.
    const audio = manifest.audio || {};
    const menuLoop = audio.menuLoop ? url(audio.menuLoop) : DEFAULT_MENU_LOOP;
    const stages =
      audio.gameStages && audio.gameStages.length ? audio.gameStages.map(url) : DEFAULT_GAME_STAGES;
    music.setTheme({ menuLoop, gameStages: stages });
    // The gunshot follows the pack too, preloading on swap so the round's first shot
    // isn't silent; a pack without one keeps the default crack. Same for the watcher's
    // wind-up cue (#53).
    setShotUrl(audio.shot ? url(audio.shot) : DEFAULT_SHOT, audio.shotGain);
    setWindupUrl(audio.windup ? url(audio.windup) : DEFAULT_WINDUP);

    currentTheme = key;
  }

  // Bring the scene up on the default theme before we join; the lobby broadcast then
  // swaps to the room's actual theme if it differs (e.g. a guest joining a western room).
  await loadTheme(DEFAULT_THEME);

  goButton.addEventListener("click", () => {
    channel.push("go", {});
    goButton.disabled = true;
    lobbyHint.textContent = "starting…";
  });

  // --- Socket / channel ---
  const { channel, teardown: closeSocket } = openChannel("room:" + room, {
    host: wantsCreate,
    name: playerName,
  });
  channel
    .join()
    .receive("ok", (resp) => {
      myName = (resp && resp.name) || "";
      // Host status comes from the server in the join reply, so the controls are
      // right immediately; the lobby broadcast keeps it current if the host changes.
      isHost = !!(resp && resp.host);
      applyHostUI();
      renderLobby();
    })
    .receive("error", (r) => {
      // The common case is a join-by-code for a lobby that isn't live — point
      // the player back home rather than leaving them on a dead Go button.
      const notFound = r && r.reason === "not_found";
      banner = notFound ? `Lobby ${room} not found` : `join failed: ${JSON.stringify(r)}`;
      lobbyCode.textContent = "";
      goButton.style.display = "none";
      lobbyLeave.style.display = "none"; // no live lobby to leave — use the home link
      lobbyHint.textContent = notFound ? "It may have already ended." : "";
      lobbyBack.hidden = false;
      renderLobby();
    });

  channel.on("lobby", (p) => {
    roster = p.players || [];
    // Host is whatever the server says (by name) — never the URL. Refresh the lobby
    // controls when it changes (first roster, or a hand-off after the host leaves).
    isHost = !!myName && p.host === myName;
    applyHostUI();
    applyMaxAmmo(p.max_ammo);
    applyMaxChances(p.max_chances);
    applyTheme(p.theme);
    applyPace(p.pace);
    applyGameMode(p.mode);
    applyVisibility(p.public);
    // Now that the knob values are current, re-derive the Custom/Standard view (mainly for
    // guests, who infer their setup from these values; a no-op for a host in a fixed setup).
    applySetup();
    if (!scores) banner = "Lobby";
    renderLobby();
  });
  // The host closed the lobby — everyone still in it gets dropped back home.
  channel.on("closed", () => {
    navigate("/");
  });
  channel.on("snapshot", (snap) => {
    music.ensureInGame();
    hideCard();
    updateWorld(snap);
  });
  // Any player's shot — including your own — arrives here, so everyone hears it (§5).
  channel.on("shot", () => playShot());
  channel.on("round_start", () => {
    music.toRound(); // open on stage 1 and climb the ladder through the round
    hideCard();
    scores = null;
    dead = false; // fresh round → back in play (a previous round's death is cleared)
    myBodyId = null; // the room re-sends our body id ("you") right after round_start
    predictedX = null;
    clearPeerCrosses(); // last round's reticles don't carry into this one
    setCrosshairVisible(true); // fresh round → fresh clip (DESIGN §5)
    showAmmo(true); // (re)load the ammo HUD to a full clip for the new round
    showChances(true); // reveal the lives HUD (only when >1 life is in play, §7)
  });
  // The room privately told us our body dropped — we're out for the round (#11, §7).
  // Drop our reticle and stop firing/aiming; peers' view is unchanged (DESIGN §5).
  channel.on("out", () => {
    dead = true;
    setCrosshairVisible(false);
    setChances(0); // "out" means no lives left; no takeover follows, so no chances update will (#64)
    myBodyId = null; // our corpse is just another body now — back to plain interpolation
    predictedX = null;
  });
  // The room privately told us which body we drive (#41) — at round start, and again
  // when a takeover moves us into a bot body (§7). Reset the prediction to seed from
  // the next snapshot, and re-assert the held keys on the new body: the server spawns
  // a taken-over body stopped, but our fingers may say otherwise.
  channel.on("you", (p) => {
    if (typeof p.id !== "number") return;
    myBodyId = p.id;
    predictedX = null;
    sendVerb();
  });
  // Private lives update for our HUD (DESIGN §7): the room sends our starting count at
  // round start and a fresh one each time we take over a bot. Peers never see this.
  channel.on("chances", (p) => {
    if (typeof p.chances === "number") setChances(p.chances);
  });
  channel.on("round_over", (p) => {
    // A player name, "Bot" when a bot crossed first, or null when every human was
    // knocked out and the round ended with no winner at all (#55).
    banner = p.winner ? `🏁 ${p.winner} wins!` : "💀 Everyone's out";
    scores = p.scores || {};
    clearPeerCrosses(); // the round's frozen — drop the peers' reticles with the card up
    setCrosshairVisible(false); // no firing while the card is up
    myBodyId = null; // stop predicting too, or held keys would slide us across the freeze
    predictedX = null;
    showAmmo(false); // the round's done — pull the HUD with the card up
    showChances(false); // pull the lives HUD too
    // Stay in the game: float the card over the frozen final frame, and duck the music to
    // its chill stage-1 limbo bed (held, not climbing) until the next round ramps anew.
    music.toCard();
    showCard(true);
  });

  // Start out in the pre-game lobby (full backdrop), waiting to hit Go. If the menu loop
  // is already playing — or its start() is mid-flight — carried over from the splash through
  // the shared audio shell when we arrived here via client-side navigation (#20), adopt it
  // without a restart so the music doesn't skip. `wanted` (not just `live`) is the fix for
  // the home→lobby skip: when the first gesture is the Create click itself, the menu loop's
  // start() is still decoding when we boot here, so a `live`-only check would miss it and
  // fire a second start() — restarting the track from the top. Otherwise start it fresh.
  if (lobbyMusic.wanted || lobbyMusic.live) music.adoptLobby();
  else music.toLobby();
  showCard(false);

  function updateWorld(snap) {
    // The watcher's light rides red-light snapshots only (#53); classic carries none,
    // which is what hides the watcher there.
    setLight(snap.light || null);

    const ents = snap.entities || [];
    const rows = Math.max(1, ents.length - 1);
    view.worldW = snap.finish_x || 1000;
    view.worldH = Math.max(1, rows * ROW_SPACING);

    const seen = new Set();
    for (const e of ents) {
      seen.add(e.id);
      const { sx, sy } = worldToScreen(e.x, e.row * ROW_SPACING, view);
      // Our own body animates off the locally-held verb rather than the snapshot's
      // copy (which trails it by the round trip), so its legs move the same frame the
      // key does (#41) — the same animations every body uses, just sourced locally.
      const mine = e.id === myBodyId;
      const state = mine && e.alive ? localState() : stateFor(e);
      let s = sprites.get(e.id);
      if (!s) {
        const variant = variantFor(e.id);
        const sprite = new AnimatedSprite(sheet.animations[`v${variant}_${state}`]);
        sprite.anchor.set(0.5);
        sprite.scale.set(SPRITE_SCALE);
        sprite.animationSpeed = ANIM_SPEED[state];
        sprite.x = sx;
        sprite.y = sy;
        sprite.play();
        entityLayer.addChild(sprite);
        s = { sprite, tx: sx, ty: sy, state, variant };
        sprites.set(e.id, s);
      }
      // Swap the animation only when the state actually changes (verb or death), so
      // we don't restart the loop every snapshot.
      if (state !== s.state) {
        s.state = state;
        s.sprite.textures = sheet.animations[`v${s.variant}_${state}`];
        s.sprite.animationSpeed = ANIM_SPEED[state];
        s.sprite.play();
      }
      s.tx = sx;
      s.ty = sy;
      s.sprite.alpha = e.alive ? 1 : 0.55; // dropped frame already reads as down; a touch of fade on top

      // Reconcile our predicted body against the server's word (#41): seed it from the
      // first snapshot that shows the body, then correct only genuine desyncs — the
      // expected in-flight trail of a moving body is left alone (prediction.mjs). The
      // ticker below re-targets this sprite from the prediction every frame.
      if (mine && e.alive) {
        predictedX = predictedX === null ? e.x : reconcile(predictedX, e.x, verb() !== "stop");
      } else if (mine) {
        // Our body shows dropped before the private "out"/"you" lands — stop predicting
        // now; that signal then settles whether we're out or in a new body (§7).
        myBodyId = null;
        predictedX = null;
      }
    }
    for (const [id, s] of sprites) {
      if (!seen.has(id)) {
        entityLayer.removeChild(s.sprite);
        s.sprite.destroy();
        sprites.delete(id);
      }
    }

    updatePeerCrosses(snap.crosshairs || []);
  }

  // Retarget the peer-reticle pool from this snapshot's anonymous point list. The list
  // is positional (the server keeps each peer in a stable slot), so slot i tracks the
  // same reticle across snapshots — that's what lets us interpolate it. We grow the
  // pool to fit and hide any slots beyond the current count (a peer who disarmed/left).
  function updatePeerCrosses(points) {
    while (peerCrosses.length < points.length) {
      const sprite = new Sprite(myCross.texture);
      sprite.anchor.set(0.5);
      sprite.visible = false;
      app.stage.addChild(sprite);
      peerCrosses.push({ sprite, cwx: 0, cwy: 0, twx: 0, twy: 0, live: false });
    }
    for (let i = 0; i < peerCrosses.length; i++) {
      const pc = peerCrosses[i];
      if (i < points.length) {
        pc.twx = points[i].x;
        pc.twy = points[i].y;
        if (!pc.live) (pc.cwx = pc.twx), (pc.cwy = pc.twy), (pc.live = true); // snap in, don't glide from origin
        pc.sprite.texture = myCross.texture; // adopt the live theme's reticle
        pc.sprite.visible = true;
      } else if (pc.live) {
        pc.sprite.visible = false;
        pc.live = false;
      }
    }
  }

  // --- Input: hold to walk, Shift to run, release to stop (§3) ---
  let walking = false;
  let running = false;
  const verb = () => (running ? "run" : walking ? "walk" : "stop");
  // The animation state our held verb maps to — what stateFor derives for everyone
  // else from the snapshot, our own body takes from the keys directly (#41).
  const localState = () => (running ? "run" : walking ? "walk" : "idle");
  const sendVerb = () => channel.push("input", { verb: verb() });

  const onKeyDown = (ev) => {
    if (ev.key === "Shift" && !running) (running = true), sendVerb();
    else if (ev.code === "Space" && !walking) (walking = true), sendVerb();
  };
  const onKeyUp = (ev) => {
    if (ev.key === "Shift") (running = false), sendVerb();
    else if (ev.code === "Space") (walking = false), sendVerb();
  };
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);

  // --- Mouse aim + the one bullet (§5) ---
  let mouse = { x: app.screen.width / 2, y: app.screen.height / 2 };
  app.canvas.addEventListener("mousemove", (ev) => {
    const r = app.canvas.getBoundingClientRect();
    mouse = { x: ev.clientX - r.left, y: ev.clientY - r.top };
  });
  // Undo the letterbox transform on the current mouse: canvas pixels → design space → world.
  const mouseToWorld = () => {
    const dx = (mouse.x - world.x) / world.scale.x;
    const dy = (mouse.y - world.y) / world.scale.y;
    return screenToWorld(dx, dy, view);
  };

  // Stream our reticle position to the room so peers can see it (DESIGN §5). Throttled
  // to roughly the snapshot rate — that's all the reticle resolution anyone gets — and
  // sent only when armed and actually moved. Once unarmed we stop: the server has already
  // dropped our reticle (it gates on ammo), so peers see it vanish with our last shot.
  let lastAimAt = 0;
  let aimSent = { x: null, y: null };
  const sendAim = () => {
    if (dead || !myCross.visible || ammo <= 0) return;
    if (mouse.x === aimSent.x && mouse.y === aimSent.y) return;
    const now = performance.now();
    if (now - lastAimAt < 50) return;
    lastAimAt = now;
    aimSent = { x: mouse.x, y: mouse.y };
    const { wx, wy } = mouseToWorld();
    channel.push("aim", { x: wx, y: wy });
  };
  // Alt-tabbing back must not waste a bullet (#65): the click that refocuses the window
  // lands on the canvas like any other, but the player meant "give me the game back",
  // not "fire". The browser fires `focus` before the click it granted focus for, so a
  // short grace after regaining focus swallows exactly that click; clicks made while
  // the game already had focus are unaffected.
  const REFOCUS_GRACE_MS = 300;
  let refocusedAt = -Infinity;
  const onWindowFocus = () => (refocusedAt = performance.now());
  window.addEventListener("focus", onWindowFocus);
  app.canvas.addEventListener("click", () => {
    if (dead || !myCross.visible || ammo <= 0) return; // out of bullets or out of the round
    if (performance.now() - refocusedAt < REFOCUS_GRACE_MS) return; // refocus click (#65)
    const { wx, wy } = mouseToWorld();
    // Firing reveals nothing about what you hit — only that you've spent a bullet (§5).
    // The SFX plays when the server broadcasts the shot back (the "shot" handler
    // above), so you hear the same crack as everyone else rather than a local one.
    // Spend the round off the *server's* reply, not optimistically: a shot the server
    // rejects (already dead, or a race against the ammo cap) replies `fired: false`, and
    // counting that locally would desync the HUD from real ammo (#11).
    channel.push("fire", { x: wx, y: wy }).receive("ok", (resp) => {
      if (!resp || !resp.fired) return;
      ammo = Math.max(0, ammo - 1);
      setAmmo(ammo);
      // Only your *last* shot disarms you: the crosshair (and the OS cursor's absence)
      // lingers while you still have bullets, and vanishes once you're empty (§5).
      if (ammo <= 0) setCrosshairVisible(false);
    });
  });

  // --- Render loop: interpolate other entities toward the latest snapshot ---
  app.ticker.add((ticker) => {
    // Throb the wind-up rim (#60) off the clock, not frames, so the pulse reads the
    // same at any refresh rate.
    if (light === "windup") lightRim.alpha = 0.4 + 0.6 * Math.abs(Math.sin(performance.now() / 130));
    for (const s of sprites.values()) {
      s.sprite.x += (s.tx - s.sprite.x) * 0.25;
      s.sprite.y += (s.ty - s.sprite.y) * 0.25;
    }
    // Our own body moves by prediction, not the snapshot lerp above (#41): advance it
    // by the held verb every frame and pin the sprite there (tx too, so the lerp
    // agrees), so a keypress shows this very frame. Corrections arrive smoothly via
    // reconcile in updateWorld; everything visual about the body stays identical.
    if (myBodyId !== null && predictedX !== null) {
      const s = sprites.get(myBodyId);
      if (s) {
        predictedX = advance(predictedX, verb(), ticker.deltaMS);
        const { sx } = worldToScreen(predictedX, 0, view);
        s.tx = sx;
        s.sprite.x = sx;
      }
    }
    myCross.x = mouse.x;
    myCross.y = mouse.y;
    // Glide each peer reticle toward its latest world point, then map that through the
    // same letterbox transform a shot uses, so it lands where its owner is aiming.
    for (const pc of peerCrosses) {
      if (!pc.sprite.visible) continue;
      pc.cwx += (pc.twx - pc.cwx) * 0.25;
      pc.cwy += (pc.twy - pc.cwy) * 0.25;
      const { sx, sy } = worldToScreen(pc.cwx, pc.cwy, view);
      pc.sprite.x = world.x + sx * world.scale.x;
      pc.sprite.y = world.y + sy * world.scale.y;
    }
    // Push our own reticle out on the same loop (self-throttling), so a parked mouse
    // still reports its resting spot — peers need to see a reticle linger on a suspect.
    sendAim();
  });

  // Teardown for client-side navigation away from the game (#20): leave the room, drop the
  // socket, and destroy the Pixi app (which removes its canvas, ticker and canvas-bound
  // listeners). The window-level listeners we added are removed explicitly. The audio shell
  // is deliberately NOT torn down — its loop keeps playing across the hop, which is the point.
  // Lobby/HUD DOM listeners aren't removed: those elements are replaced wholesale by the
  // router's content swap, so they're collected with the old DOM.
  return () => {
    window.removeEventListener("resize", layout);
    window.removeEventListener("keydown", onKeyDown);
    window.removeEventListener("keyup", onKeyUp);
    window.removeEventListener("focus", onWindowFocus);
    // Destroy the Pixi app first: its render loop pushes "aim" over the channel, so stop
    // the ticker before we leave the room. `removeView` drops the canvas (the router's
    // content swap would discard it anyway, but don't rely on that here).
    try {
      app.destroy({ removeView: true }, { children: true });
    } catch {
      /* already destroyed */
    }
    closeSocket();
  };
}
