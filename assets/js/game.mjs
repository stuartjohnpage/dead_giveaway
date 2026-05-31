// Dead Giveaway browser client (DESIGN §9): connects the websocket, joins a room,
// and renders the authoritative snapshots with Pixi. Pure math lives in
// coords.mjs (unit-tested); this module is the Pixi + socket + input glue.

import { Application, Graphics, Sprite } from "pixi.js";
import { Socket } from "phoenix";
import { worldToScreen, screenToWorld } from "./coords.mjs";

const PAD = 24;
const ROW_SPACING = 10; // must match DeadGiveaway.World @row_spacing

export async function boot() {
  const mount = document.getElementById("game");
  if (!mount) return;

  const room = mount.dataset.room;
  // The host (from /play/new) starts the room; a join-by-code requires it to
  // already exist (the server replies "not_found" otherwise).
  const isHost = mount.dataset.host === "true";

  const app = new Application();
  // The canvas tracks the window, so the game owns the whole viewport.
  await app.init({ resizeTo: window, background: "#0b1020", antialias: true });
  mount.appendChild(app.canvas);

  // Figures and the crosshair are drawn with Graphics and baked into textures
  // up front — synchronously, with no async asset decode that could drop the
  // first frame (the old SVG load rendered for some players but not others).
  //
  // Placeholder cosmetic pool (DESIGN §4): a handful of tinted figures standing
  // in for real sprite art. Assignment is by a hash of the entity id (below) —
  // stable across clients and deliberately *independent* of the human/bot
  // mapping, so the sprite never hints at who is human. Swap these generated
  // textures for loaded sprite images when art is ready; nothing else changes.
  const runnerTexs = [0xdfe7ff, 0xf6c177, 0x9ece6a, 0x7aa2f7, 0xbb9af7, 0xf7768e].map(
    (color) => app.renderer.generateTexture(new Graphics().circle(0, 0, 7).fill(color)),
  );
  // Cheap integer hash so id→sprite looks scattered rather than a row-by-row
  // cycle, while staying deterministic (same id → same sprite for every client).
  const texFor = (id) => runnerTexs[(Math.imul(id ^ 0x9e3779b9, 0x85ebca6b) >>> 0) % runnerTexs.length];

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

  const sprites = new Map(); // entity id -> { sprite, tx, ty }
  const view = { worldW: 1000, worldH: 50, screenW: app.screen.width, screenH: app.screen.height, pad: PAD };
  const syncScreen = () => {
    view.screenW = app.screen.width;
    view.screenH = app.screen.height;
  };
  window.addEventListener("resize", syncScreen);

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
    syncScreen();
    view.worldW = snap.finish_x || 1000;
    view.worldH = Math.max(1, rows * ROW_SPACING);

    const seen = new Set();
    for (const e of ents) {
      seen.add(e.id);
      const { sx, sy } = worldToScreen(e.x, e.row * ROW_SPACING, view);
      let s = sprites.get(e.id);
      if (!s) {
        const sprite = new Sprite(texFor(e.id));
        sprite.anchor.set(0.5);
        sprite.x = sx;
        sprite.y = sy;
        app.stage.addChild(sprite);
        s = { sprite, tx: sx, ty: sy };
        sprites.set(e.id, s);
      }
      s.tx = sx;
      s.ty = sy;
      s.sprite.alpha = e.alive ? 1 : 0.2; // dead = ghosted, still shown
    }
    for (const [id, s] of sprites) {
      if (!seen.has(id)) {
        app.stage.removeChild(s.sprite);
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
    const { wx, wy } = screenToWorld(mouse.x, mouse.y, view);
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
