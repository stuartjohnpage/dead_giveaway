// Dead Giveaway browser client (DESIGN §9): connects the websocket, joins a room,
// and renders the authoritative snapshots with Pixi. Pure math lives in
// coords.mjs (unit-tested); this module is the Pixi + socket + input glue.

import { Application, AnimatedSprite, Assets, Container, Graphics, Sprite, TilingSprite } from "pixi.js";
import { Socket } from "phoenix";
import { worldToScreen, screenToWorld } from "./coords.mjs";

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

// Theme asset pack — see priv/static/images/themes/<THEME>/README.md. Swapping the
// whole look = changing this key. Cosmetic variants are NOT tied to the human/bot
// mapping (DESIGN §4, §9).
const THEME = "neon";
const themePath = (file) => `/images/themes/${THEME}/${file}`;
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
  // The host (from /play/new) starts the room; a join-by-code requires it to
  // already exist (the server replies "not_found" otherwise).
  const isHost = mount.dataset.host === "true";

  const app = new Application();
  // The canvas tracks the window; the world container (below) is letterbox-scaled to
  // fit it. antialias off + nearest-neighbour scaling keeps the pixel art crisp.
  await app.init({ resizeTo: window, background: "#0b1020", antialias: false });
  mount.appendChild(app.canvas);

  // Load the theme's sprite atlas (12 cosmetic variants × idle/walk/run/dropped) and
  // the backdrop art up front. boot() runs while the lobby overlay is showing and a
  // round only starts on the Go button, so this decode never races the first frame —
  // unlike the old async SVG load, which rendered for some players but not others.
  const sheet = await Assets.load(themePath("agents.json"));
  for (const tex of Object.values(sheet.textures)) tex.source.scaleMode = "nearest";
  const [arenaTex, finishTex, floorTex] = await Promise.all(
    ["arena_bg.png", "finish_line.png", "floor_tile.png"].map((f) => Assets.load(themePath(f))),
  );
  for (const t of [arenaTex, finishTex, floorTex]) t.source.scaleMode = "nearest";

  // World-space scene graph, all under one container we scale to fit the window.
  // Layers back→front: arena backdrop, tiled floor band, finish line, runners.
  const world = new Container();
  app.stage.addChild(world);

  const arena = new Sprite(arenaTex);
  arena.width = DESIGN_W;
  arena.height = DESIGN_H;
  world.addChild(arena);

  const floor = new TilingSprite({ texture: floorTex, width: DESIGN_W, height: FLOOR_H });
  floor.y = FLOOR_TOP;
  world.addChild(floor);

  // worldW always equals finish_x, so the finish maps to the right margin regardless
  // of the configured value — its screen position is fixed.
  const finish = new Sprite(finishTex);
  finish.anchor.set(0.5, 0);
  finish.x = DESIGN_W - PAD;
  finish.y = FLOOR_TOP;
  finish.height = FLOOR_H;
  world.addChild(finish);

  const entityLayer = new Container();
  world.addChild(entityLayer);

  // Cheap integer hash so id→variant looks scattered rather than a row-by-row cycle,
  // while staying deterministic (same id → same look for every client) and
  // independent of the human/bot mapping, so the sprite never hints at who is human.
  const variantFor = (id) =>
    String((Math.imul(id ^ 0x9e3779b9, 0x85ebca6b) >>> 0) % VARIANTS).padStart(2, "0");

  const crossTex = app.renderer.generateTexture(
    new Graphics()
      .circle(0, 0, 11)
      .stroke({ width: 2, color: 0xff5577 })
      .moveTo(-15, 0)
      .lineTo(15, 0)
      .moveTo(0, -15)
      .lineTo(0, 15)
      .stroke({ width: 2, color: 0xff5577 }),
  );

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

  // Crosshair lives in screen space so it tracks the raw mouse with no transform.
  const myCross = new Sprite(crossTex);
  myCross.anchor.set(0.5);
  app.stage.addChild(myCross);

  // --- Audio volume settings (persisted client-side) ---
  // Each channel is a 0–100 percentage; master scales the lot. SFX is the only
  // channel today — music is issue #3. Effective gain is master × channel.
  const VOL_KEY = "dg:volume";
  const defaultVol = { master: 100, sfx: 70 };
  const loadVol = () => {
    try {
      return { ...defaultVol, ...JSON.parse(localStorage.getItem(VOL_KEY) || "{}") };
    } catch {
      return { ...defaultVol }; // private mode / corrupt value → fall back to defaults
    }
  };
  const volume = loadVol();
  const saveVol = () => {
    try {
      localStorage.setItem(VOL_KEY, JSON.stringify(volume));
    } catch {
      /* storage unavailable (private mode) — settings just won't persist */
    }
  };
  const sfxGain = () => (volume.master / 100) * (volume.sfx / 100);

  // Firing SFX — preloaded so the first shot isn't silent while the asset decodes.
  // Pixabay Content License, credited in priv/static/assets/sounds/CREDITS.md.
  const shotSfx = new Audio("/assets/sounds/gunshot.mp3");
  shotSfx.preload = "auto";
  const playShot = () => {
    // cloneNode lets overlapping shots both play — the server broadcasts every
    // peer's fire, so several can land on the same tick.
    const s = shotSfx.cloneNode();
    s.volume = sfxGain();
    s.play().catch(() => {}); // browsers reject autoplay until first gesture — the click *is* the gesture, so this should always succeed here
  };

  // --- Lobby overlay (the default view; hidden only while a round runs) ---
  // These all ship together in game_html/show.html.heex, so we resolve them
  // once and trust they're present rather than nil-guarding every use.
  const lobby = document.getElementById("lobby");
  const lobbyBanner = document.getElementById("lobby-banner");
  const lobbyCode = document.getElementById("lobby-code");
  const lobbyList = document.getElementById("lobby-list");
  const lobbyHint = document.getElementById("lobby-hint");
  const lobbyBack = document.getElementById("lobby-back");
  const goButton = document.getElementById("go");

  // Show the shareable code so the host can pass it to friends.
  lobbyCode.textContent = `Lobby ${room}`;

  let myName = "";
  let banner = "Lobby — waiting to start";
  let roster = [];
  let scores = null; // set after a round; shown until the next round starts

  const renderLobby = () => {
    lobbyBanner.textContent = banner;
    goButton.textContent = scores ? "Play again" : "Go";
    lobbyList.innerHTML = "";
    const rows = scores
      ? Object.entries(scores)
          .sort((a, b) => b[1] - a[1])
          .map(([n, w]) => (n === myName ? `${n} (you) — ${w}` : `${n} — ${w}`))
      : roster.map((n) => (n === myName ? `${n} (you)` : n));
    for (const text of rows) {
      const li = document.createElement("li");
      li.textContent = text;
      lobbyList.appendChild(li);
    }
  };
  const showLobby = () => {
    renderLobby();
    goButton.disabled = false;
    lobbyHint.textContent = "";
    lobby.style.display = "flex";
  };
  const hideLobby = () => (lobby.style.display = "none");

  goButton.addEventListener("click", () => {
    channel.push("go", {});
    goButton.disabled = true;
    lobbyHint.textContent = "starting…";
  });

  // --- Volume sliders (in the lobby card) ---
  // Reflect the stored level, then write changes straight back to `volume` and
  // localStorage so the next shot is at the new gain — no reload needed.
  const bindSlider = (key) => {
    const input = document.getElementById(`vol-${key}`);
    const valOut = document.getElementById(`vol-${key}-val`);
    if (!input) return;
    const show = () => valOut && (valOut.textContent = `${volume[key]}%`);
    input.value = String(volume[key]);
    show();
    input.addEventListener("input", () => {
      volume[key] = Number(input.value);
      show();
      saveVol();
    });
  };
  bindSlider("master");
  bindSlider("sfx");

  // --- Socket / channel ---
  const socket = new Socket("/socket", {});
  socket.connect();
  const channel = socket.channel("room:" + room, { host: isHost });
  channel
    .join()
    .receive("ok", (resp) => {
      myName = (resp && resp.name) || "";
      renderLobby();
    })
    .receive("error", (r) => {
      // The common case is a join-by-code for a lobby that isn't live — point
      // the player back home rather than leaving them on a dead Go button.
      const notFound = r && r.reason === "not_found";
      banner = notFound ? `Lobby ${room} not found` : `join failed: ${JSON.stringify(r)}`;
      lobbyCode.textContent = "";
      goButton.style.display = "none";
      lobbyHint.textContent = notFound ? "It may have already ended." : "";
      lobbyBack.hidden = false;
      renderLobby();
    });

  channel.on("lobby", (p) => {
    roster = p.players || [];
    if (!scores) banner = "Lobby — waiting to start";
    renderLobby();
  });
  channel.on("snapshot", (snap) => {
    hideLobby();
    updateWorld(snap);
  });
  // Any player's shot — including your own — arrives here, so everyone hears it (§5).
  channel.on("shot", () => playShot());
  channel.on("round_start", () => {
    hideLobby();
    scores = null;
    myCross.visible = true; // fresh round → fresh bullet (DESIGN §5)
  });
  channel.on("round_over", (p) => {
    // The winner is always set now — a player name, or "Bot" when a bot crossed first.
    banner = p.winner ? `🏁 ${p.winner} wins!` : "Round over";
    scores = p.scores || {};
    showLobby();
  });

  // Start out in the lobby, waiting to hit Go.
  showLobby();

  function updateWorld(snap) {
    const ents = snap.entities || [];
    const rows = Math.max(1, ents.length - 1);
    view.worldW = snap.finish_x || 1000;
    view.worldH = Math.max(1, rows * ROW_SPACING);

    const seen = new Set();
    for (const e of ents) {
      seen.add(e.id);
      const { sx, sy } = worldToScreen(e.x, e.row * ROW_SPACING, view);
      const state = stateFor(e);
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
    }
    for (const [id, s] of sprites) {
      if (!seen.has(id)) {
        entityLayer.removeChild(s.sprite);
        s.sprite.destroy();
        sprites.delete(id);
      }
    }
  }

  // --- Input: hold to walk, Shift to run, release to stop (§3) ---
  let walking = false;
  let running = false;
  const verb = () => (running ? "run" : walking ? "walk" : "stop");
  const sendVerb = () => channel.push("input", { verb: verb() });

  window.addEventListener("keydown", (ev) => {
    if (ev.key === "Shift" && !running) (running = true), sendVerb();
    else if (ev.code === "Space" && !walking) (walking = true), sendVerb();
  });
  window.addEventListener("keyup", (ev) => {
    if (ev.key === "Shift") (running = false), sendVerb();
    else if (ev.code === "Space") (walking = false), sendVerb();
  });

  // --- Mouse aim + the one bullet (§5) ---
  let mouse = { x: app.screen.width / 2, y: app.screen.height / 2 };
  app.canvas.addEventListener("mousemove", (ev) => {
    const r = app.canvas.getBoundingClientRect();
    mouse = { x: ev.clientX - r.left, y: ev.clientY - r.top };
  });
  app.canvas.addEventListener("click", () => {
    if (!myCross.visible) return; // already fired — defenceless
    // Undo the letterbox transform: canvas pixels → design space → world.
    const dx = (mouse.x - world.x) / world.scale.x;
    const dy = (mouse.y - world.y) / world.scale.y;
    const { wx, wy } = screenToWorld(dx, dy, view);
    // Firing reveals nothing about what you hit — only that you're now unarmed (§5).
    // The SFX plays when the server broadcasts the shot back (the "shot" handler
    // above), so you hear the same crack as everyone else rather than a local one.
    channel.push("fire", { x: wx, y: wy });
    myCross.visible = false; // your crosshair vanishes once you've fired (§5)
  });

  // --- Render loop: interpolate other entities toward the latest snapshot ---
  app.ticker.add(() => {
    for (const s of sprites.values()) {
      s.sprite.x += (s.tx - s.sprite.x) * 0.25;
      s.sprite.y += (s.ty - s.sprite.y) * 0.25;
    }
    myCross.x = mouse.x;
    myCross.y = mouse.y;
  });
}
