// Dead Giveaway browser client (DESIGN §9): connects the websocket, joins a room,
// and renders the authoritative snapshots with Pixi. Pure math lives in
// coords.mjs (unit-tested); this module is the Pixi + socket + input glue.

import { Application, AnimatedSprite, Assets, Container, Graphics, Sprite, Texture, TilingSprite } from "pixi.js";
import { Socket } from "phoenix";
import { worldToScreen, screenToWorld } from "./coords.mjs";
import { loadVolume, sfxGain } from "./volume.mjs";
import { createMusicLoop, createEscalatingLoop, audioRunning, MUSIC_GAIN } from "./music.mjs";

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
// Fallbacks when a pack's manifest omits its audio (e.g. a new theme whose escalating
// game stages aren't generated yet): reuse the default theme's tracks rather than go silent.
const DEFAULT_MENU_LOOP = `${themeBase(DEFAULT_THEME)}/menu_loop.mp3`;
const DEFAULT_GAME_STAGES = [1, 2, 3, 4].map((i) => `${themeBase(DEFAULT_THEME)}/game/stage${i}.mp3`);
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
  // `data-host` (set by /play/new) only asks the server to *create* this room; a
  // join-by-code requires it to already exist (the server replies "not_found"
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
  await app.init({ resizeTo: window, background: "#0b1020", antialias: false });
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
  // of the configured value — its screen position is fixed.
  const finish = new Sprite(Texture.EMPTY);
  finish.anchor.set(0.5, 0);
  finish.x = DESIGN_W - PAD;
  finish.y = FLOOR_TOP;
  world.addChild(finish);

  const entityLayer = new Container();
  world.addChild(entityLayer);

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
  // texture (a cross tinted to the theme's accent) is generated in loadTheme.
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

  // Audio volume is configured on the home page and kept in sessionStorage
  // (volume.mjs); we read the stored level at boot and apply it to the SFX gain.
  const volume = loadVolume();

  // Two background tracks: the menu/lobby loop and the four-stage escalating in-game
  // loop. The game loop covers both the live round AND the between-rounds "Play again?"
  // card — we never drop back to the menu loop once a round has started, since the
  // player now stays in the game. Both honour the master sound switch.
  // Both loops are retargeted per theme by loadTheme (setUrl/setUrls); they start on the
  // default theme's tracks. The escalating loop climbs stage1→stage4 over the round (one
  // stage per 15s, holding at stage 4); a round opens on its chill stage-1 bed.
  const lobbyMusic = createMusicLoop(DEFAULT_MENU_LOOP);
  const gameMusic = createEscalatingLoop(DEFAULT_GAME_STAGES);
  const musicGain = () => (volume.enabled ? (volume.master / 100) * MUSIC_GAIN : 0);
  // Which loop belongs to the current view: false = pre-game lobby (menu track),
  // true = in the game (live round or the post-round card). null until the first edge.
  let inGame = null;
  // What to (re)play on the autoplay-unlock gesture — kept current as the view changes.
  let replayMusic = () => {};
  // Swap to the lobby loop (stop game music, start lobby music from the top).
  const playLobbyMusic = () => {
    gameMusic.stop();
    if (volume.enabled) lobbyMusic.start(musicGain());
  };
  // Swap to the in-game loop. `escalate` true climbs the stages (a live round); false
  // holds the chill stage-1 bed (the between-rounds card).
  const playGameMusic = (escalate) => {
    lobbyMusic.stop();
    if (volume.enabled) gameMusic.start(musicGain(), { escalate });
  };
  // Enter the lobby track (pre-game only).
  const toLobbyMusic = () => {
    inGame = false;
    replayMusic = playLobbyMusic;
    playLobbyMusic();
  };
  // Open a round on the climbing game track (stage 1, ramping up).
  const toRoundMusic = () => {
    inGame = true;
    replayMusic = () => playGameMusic(true);
    playGameMusic(true);
  };
  // The between-rounds card: reset the game track to its chill stage-1 bed and hold.
  const toCardMusic = () => {
    inGame = true;
    replayMusic = () => playGameMusic(false);
    playGameMusic(false);
  };
  // Make sure the game loop is the one playing, in case a snapshot ever beats its
  // round_start to the client (a no-op once we're already in the game).
  const ensureGameMusic = () => {
    if (!inGame) toRoundMusic();
  };
  // Autoplay policy re-arms on every page load, so the loop queued at boot can't
  // actually sound until the first user gesture — (re)start the matching loop then to
  // unlock the shared AudioContext. This must fire EXACTLY ONCE across both gesture
  // types: otherwise the gesture that doesn't trigger it (e.g. the first spacebar after
  // a Go click already primed via pointerdown) would re-run replayMusic and restart the
  // track mid-round. So one guard removes both listeners on the first gesture.
  //
  // And only replay when the context is still SUSPENDED. Where autoplay is permitted
  // (high media-engagement), the boot-time start() is already sounding — so the first
  // gesture (e.g. clicking the lobby's bullet-count select) must not restart it from the
  // top. When suspended, the queued loop is silent and replaying is what unlocks it.
  let primed = false;
  const primeMusic = () => {
    if (primed) return;
    primed = true;
    window.removeEventListener("pointerdown", primeMusic);
    window.removeEventListener("keydown", primeMusic);
    if (!audioRunning()) replayMusic();
  };
  window.addEventListener("pointerdown", primeMusic);
  window.addEventListener("keydown", primeMusic);

  // Firing SFX — preloaded so the first shot isn't silent while the asset decodes.
  // Pixabay Content License, credited in priv/static/sounds/CREDITS.md.
  const shotSfx = new Audio("/sounds/gunshot.mp3");
  shotSfx.preload = "auto";
  const playShot = () => {
    // cloneNode lets overlapping shots both play — the server broadcasts every
    // peer's fire, so several can land on the same tick.
    const s = shotSfx.cloneNode();
    s.volume = sfxGain(volume);
    s.play().catch(() => {}); // browsers reject autoplay until first gesture — the click *is* the gesture, so this should always succeed here
  };

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
  const ammoSelect = document.getElementById("ammo-select");
  const themeSelect = document.getElementById("theme-select");

  // Bullets-per-round is the host's call: guests see a disabled select reflecting the
  // host's choice (kept current by the lobby broadcast). The host's changes push to the
  // room, which clamps and re-broadcasts the value to everyone. The disabled state is
  // driven by applyHostUI (below), since who hosts can change.
  ammoSelect.addEventListener("change", () => {
    channel.push("set_config", { max_ammo: Number(ammoSelect.value) });
  });
  // Mirror the room's setting into the control (and our local maxAmmo) from a broadcast.
  const applyMaxAmmo = (n) => {
    if (typeof n !== "number") return;
    maxAmmo = n;
    ammoSelect.value = String(n);
  };

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

  // --- In-round ammo HUD: your bullets for the round (DESIGN §5) ---
  const hudAmmo = document.getElementById("hud-ammo");
  const ammoBullet = document.getElementById("ammo-bullet");
  const ammoCount = document.getElementById("ammo-count");
  // Bullets the host grants per round (from the lobby broadcast) and how many of those
  // are still in hand this round. A fresh round reloads `ammo` back up to `maxAmmo`.
  let maxAmmo = 1;
  let ammo = 1;
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

  // Backing out is destructive for the host (it closes the lobby for everyone); the
  // label (set by applyHostUI) says so, while a guest only leaves their own seat.
  lobbyLeave.addEventListener("click", () => {
    channel.push("leave", {});
    window.location.href = "/";
  });

  // Reflect our server-assigned host status in the lobby controls: only the host can
  // change the bullet count / theme or close the whole lobby. Re-run from the lobby
  // roster whenever the host changes (e.g. the old host left and the room handed off).
  const applyHostUI = () => {
    ammoSelect.disabled = !isHost;
    themeSelect.disabled = !isHost;
    lobbyLeave.textContent = isHost ? "Close lobby" : "Leave lobby";
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
          .map(([n, w]) => (n === myName ? `${n} (you): ${w}` : `${n}: ${w}`))
      : roster.map((n) => (n === myName ? `${n} (you)` : n));
    for (const text of rows) {
      const li = document.createElement("li");
      li.textContent = text;
      lobbyList.appendChild(li);
    }
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
    goButton.disabled = false;
    lobbyHint.textContent = "";
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
    finish.texture = finishTex;
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

    const ui = manifest.ui || {};

    // Reticle: the same cross shape, tinted to the theme's accent.
    const reticle = ui.reticle || "#ff5577";
    const newCross = app.renderer.generateTexture(
      new Graphics()
        .circle(0, 0, 11)
        .stroke({ width: 2, color: reticle })
        .moveTo(-15, 0)
        .lineTo(15, 0)
        .moveTo(0, -15)
        .lineTo(0, 15)
        .stroke({ width: 2, color: reticle }),
    );
    const oldCross = myCross.texture;
    myCross.texture = newCross;
    if (oldCross && oldCross !== Texture.EMPTY) oldCross.destroy(true);

    // Ammo HUD icon (the theme's bullet).
    if (ui.bullet) ammoBullet.src = url(ui.bullet);

    // Lobby backdrop: stash the themed image; apply it now only if the full lobby is up
    // (the overlay card stays transparent so the game shows through).
    if (a.lobbyBackground) {
      lobbyBg = `url(${url(a.lobbyBackground)})`;
      if (lobbyShowingFull) lobby.style.backgroundImage = lobbyBg;
    }

    // Music: lobby loop + escalating game stages, falling back to the default theme's
    // tracks if this pack hasn't declared (or generated) its own yet.
    const audio = manifest.audio || {};
    const menuLoop = audio.menuLoop ? url(audio.menuLoop) : DEFAULT_MENU_LOOP;
    const stages =
      audio.gameStages && audio.gameStages.length ? audio.gameStages.map(url) : DEFAULT_GAME_STAGES;
    lobbyMusic.setUrl(menuLoop);
    gameMusic.setUrls(stages);

    const isSwap = currentTheme !== null;
    currentTheme = key;
    // On a live swap, restart whatever loop is currently playing so it picks up the new
    // track; the initial boot load leaves first playback to the toLobbyMusic() call below.
    if (isSwap) replayMusic();
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
  const socket = new Socket("/socket", {});
  socket.connect();
  const channel = socket.channel("room:" + room, { host: wantsCreate, name: playerName });
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
    applyTheme(p.theme);
    if (!scores) banner = "Lobby";
    renderLobby();
  });
  // The host closed the lobby — everyone still in it gets dropped back home.
  channel.on("closed", () => {
    window.location.href = "/";
  });
  channel.on("snapshot", (snap) => {
    ensureGameMusic();
    hideCard();
    updateWorld(snap);
  });
  // Any player's shot — including your own — arrives here, so everyone hears it (§5).
  channel.on("shot", () => playShot());
  channel.on("round_start", () => {
    toRoundMusic(); // open on stage 1 and climb the ladder through the round
    hideCard();
    scores = null;
    clearPeerCrosses(); // last round's reticles don't carry into this one
    setCrosshairVisible(true); // fresh round → fresh clip (DESIGN §5)
    showAmmo(true); // (re)load the ammo HUD to a full clip for the new round
  });
  channel.on("round_over", (p) => {
    // The winner is always set now — a player name, or "Bot" when a bot crossed first.
    banner = p.winner ? `🏁 ${p.winner} wins!` : "Round over";
    scores = p.scores || {};
    clearPeerCrosses(); // the round's frozen — drop the peers' reticles with the card up
    setCrosshairVisible(false); // no firing while the card is up
    showAmmo(false); // the round's done — pull the HUD with the card up
    // Stay in the game: float the card over the frozen final frame, and drop the music
    // back to its chill stage-1 bed (held, not climbing) so the next round ramps anew.
    toCardMusic();
    showCard(true);
  });

  // Start out in the pre-game lobby (full backdrop), waiting to hit Go.
  toLobbyMusic();
  showCard(false);

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
    if (!myCross.visible || ammo <= 0) return;
    if (mouse.x === aimSent.x && mouse.y === aimSent.y) return;
    const now = performance.now();
    if (now - lastAimAt < 50) return;
    lastAimAt = now;
    aimSent = { x: mouse.x, y: mouse.y };
    const { wx, wy } = mouseToWorld();
    channel.push("aim", { x: wx, y: wy });
  };
  app.canvas.addEventListener("click", () => {
    if (!myCross.visible || ammo <= 0) return; // out of bullets — defenceless
    const { wx, wy } = mouseToWorld();
    // Firing reveals nothing about what you hit — only that you've spent a bullet (§5).
    // The SFX plays when the server broadcasts the shot back (the "shot" handler
    // above), so you hear the same crack as everyone else rather than a local one.
    channel.push("fire", { x: wx, y: wy });
    // Spend a round locally — the server enforces the same cap, so this stays in sync.
    ammo = Math.max(0, ammo - 1);
    setAmmo(ammo);
    // Only your *last* shot disarms you: the crosshair (and the OS cursor's absence)
    // lingers while you still have bullets, and vanishes once you're empty (§5).
    if (ammo <= 0) setCrosshairVisible(false);
  });

  // --- Render loop: interpolate other entities toward the latest snapshot ---
  app.ticker.add(() => {
    for (const s of sprites.values()) {
      s.sprite.x += (s.tx - s.sprite.x) * 0.25;
      s.sprite.y += (s.ty - s.sprite.y) * 0.25;
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
}
