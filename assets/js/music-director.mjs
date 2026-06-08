// The music/view director (DESIGN §9): the policy that decides which background loop
// belongs to the current view and when to (re)play it. Lifted out of game.mjs's boot()
// closure — where it lived as mutable `inGame`/`primed`/`replayMusic` latches and a wad
// of prose comments — so the one substantial piece of untested client logic can be
// driven and asserted in isolation (music-director.test.mjs), with no DOM, no Pixi, and
// no real AudioContext.
//
// Ports & Adapters: the director is pure policy against one injected `AudioPort`, its
// entire boundary to WebAudio. It never touches AudioContext, window, or music.mjs —
// game.mjs wires a production adapter around createMusicLoop/createEscalatingLoop, and
// the test wires an in-memory recorder. (The production adapter below — createAudioPort —
// is the part that DOES wrap music.mjs, so it imports the shared fade/duck constants; the
// director proper stays pure.)

import { FADE_MS, DUCK_LEVEL } from "./music.mjs";

/**
 * The injected capability — the ONLY boundary to WebAudio.
 *
 * @typedef {Object} AudioPort
 * @property {(name: "lobby"|"game", opts: {gain: number, escalate?: boolean}) => void} play
 *   Start a loop. Starting one stops the other (the adapter's job). The director always
 *   passes the current `gain()`; the adapter declines to actually sound it at gain 0, so
 *   a muted view issues the play but stays silent.
 * @property {() => number} gain
 *   Current music gain, read fresh per transition so a mid-game mute/level change lands.
 * @property {() => boolean} audioRunning
 *   Is the shared AudioContext actually sounding? Drives the suspended-only prime guard.
 * @property {(name: "lobby"|"game", urls: string|string[]) => void} retarget
 *   Point a loop at a theme's track(s); no restart (the caller decides whether to replay).
 * @property {(opts: {gain: number, escalate: boolean, fromLobby: boolean}) => void} enterRound
 *   Open a round. `fromLobby` crossfades the menu loop out and the game loop in; otherwise
 *   the game loop is already running (ducked on the card) and just un-ducks + restages.
 * @property {(opts: {gain: number}) => void} enterCard
 *   The between-rounds card: hold the stage-1 bed and duck the game loop to limbo, in place.
 */

/**
 * Create a music director over an {@link AudioPort}.
 *
 * @param {AudioPort} audio
 * @returns {{
 *   toLobby(): void,
 *   toRound(): void,
 *   toCard(): void,
 *   ensureInGame(): void,
 *   setTheme(theme: {menuLoop: string, gameStages: string[]}): void,
 *   prime(): boolean,
 *   readonly inGame: boolean | null,
 * }}
 */
export function createMusicDirector(audio) {
  // The view this loop belongs to: false = pre-game lobby (menu track), true = in the
  // game (live round or the post-round card), null until the first edge. The edge to
  // `true` is one-way — once a round has started we never drop back to the menu loop,
  // since the player now stays in the game (DESIGN §7, §8).
  let inGame = null;

  // What the autoplay-unlock gesture / a live theme swap should (re)play — recomputed per
  // transition so callers never have to hold the closure.
  let replay = () => {};

  // The prime-once latch: the autoplay unlock must consume EXACTLY ONE gesture across
  // both gesture types (pointerdown + keydown), or the second would re-run `replay` and
  // restart the track mid-round.
  let primed = false;

  // Boot-load vs live-swap discrimination: a theme's first load leaves first playback to
  // the initial toLobby(); a later (host-picked) swap restarts whatever is playing so it
  // adopts the new track. False until the first setTheme.
  let themed = false;

  const playLobby = () => audio.play("lobby", { gain: audio.gain() });
  const playGame = (escalate) => audio.play("game", { gain: audio.gain(), escalate });

  // Enter the pre-game lobby track (only reachable before the first round).
  const toLobby = () => {
    inGame = false;
    replay = playLobby;
    playLobby();
  };

  // Adopt an already-playing lobby loop as the current view WITHOUT (re)playing it. Used
  // when the menu loop has been started elsewhere and is still sounding — the home splash,
  // whose music carries into the lobby across client-side navigation (#20) — so arriving
  // in the lobby doesn't cut the track by restarting it. Sets the same state toLobby would
  // (so a later prime()/setTheme replays the lobby loop) but issues no play.
  const adoptLobby = () => {
    inGame = false;
    replay = playLobby;
  };

  // Open a round on the climbing game track (stage 1, ramping up). `fromLobby` (we were
  // still on the menu loop) tells the adapter to crossfade the menu out and the game in;
  // otherwise we're coming back from the between-rounds card, where the game loop is still
  // running (ducked) and just needs to un-duck and restage the climb in place — no restart,
  // so the beat carries unbroken between rounds.
  const toRound = () => {
    const fromLobby = !inGame; // null/false → still on the menu loop
    inGame = true;
    replay = () => playGame(true); // the unlock/theme-swap path still does a clean (re)start
    audio.enterRound({ gain: audio.gain(), escalate: true, fromLobby });
  };

  // The between-rounds card: hold the chill stage-1 bed and duck the game track to a low
  // limbo level until the next round — in place, no restart (DESIGN §7, §8).
  const toCard = () => {
    inGame = true;
    replay = () => playGame(false);
    audio.enterCard({ gain: audio.gain() });
  };

  // Make sure the game loop is playing, for a snapshot that beats its round_start to the
  // client. Idempotent — a no-op once we're already in the game.
  const ensureInGame = () => {
    if (!inGame) toRound();
  };

  // Point both loops at a theme's tracks. The boot-time load only retargets (first
  // playback is the initial toLobby()); a live swap also restarts whichever loop is
  // currently playing so it picks up the new track.
  const setTheme = ({ menuLoop, gameStages }) => {
    audio.retarget("lobby", menuLoop);
    audio.retarget("game", gameStages);
    if (themed) replay();
    themed = true;
  };

  // The autoplay unlock. Returns whether it consumed the gesture (true exactly once, on
  // the first call) so the caller can remove its listeners. Only actually replays while
  // the context is still SUSPENDED: where autoplay is permitted the boot-time start() is
  // already sounding, so the first gesture must not restart it from the top.
  const prime = () => {
    if (primed) return false;
    primed = true;
    if (!audio.audioRunning()) replay();
    return true;
  };

  return {
    toLobby,
    adoptLobby,
    toRound,
    toCard,
    ensureInGame,
    setTheme,
    prime,
    get inGame() {
      return inGame;
    },
  };
}

/**
 * The production {@link AudioPort}: a dumb adapter over the two music loops, owning the
 * mechanical concerns the director shouldn't — starting one loop stops the other, and a
 * gain-0 (muted) play sounds nothing — so the director stays pure policy. Exported so this
 * boundary logic (notably the gain-0 silence guard) is testable with fake loops rather
 * than buried in boot().
 *
 * @param {{
 *   lobbyMusic: {start: (g: number) => void, stop: () => void, setUrl: (u: string) => void},
 *   gameMusic: {start: (g: number, opts: {escalate?: boolean}) => void, stop: () => void, setUrls: (u: string[]) => void},
 *   audioRunning: () => boolean,
 *   gain: () => number,
 * }} deps
 * @returns {AudioPort}
 */
export function createAudioPort({ lobbyMusic, gameMusic, audioRunning, gain }) {
  return {
    // Hard (re)start, stopping the other loop — the unlock/theme-swap path, where a clean
    // restart is wanted anyway. The smooth view transitions go through enterRound/enterCard.
    play(name, { gain: g, escalate }) {
      if (name === "lobby") {
        gameMusic.stop();
        if (g > 0) lobbyMusic.start(g);
      } else {
        lobbyMusic.stop();
        if (g > 0) gameMusic.start(g, { escalate });
      }
    },
    enterRound({ gain: g, escalate, fromLobby }) {
      if (fromLobby) {
        // Crossfade off the menu loop onto the game loop. The menu loop is ducked to
        // silence but left running (cheap, one source) — enterMenu fades it back up if we
        // ever return home; nothing else re-levels a backgrounded loop.
        lobbyMusic.fadeTo(0, FADE_MS);
        if (g > 0) gameMusic.start(g, { escalate, fadeMs: FADE_MS });
      } else if (g > 0) {
        // Back from the card: un-duck and restage the climb in place (no restart). If a
        // muted round meant the loop was never started, bring it up fresh instead.
        if (gameMusic.live) {
          gameMusic.restage({ escalate });
          gameMusic.fadeTo(g, FADE_MS);
        } else {
          gameMusic.start(g, { escalate, fadeMs: FADE_MS });
        }
      } else {
        gameMusic.fadeTo(0, FADE_MS); // muted — keep it silent
      }
    },
    enterCard({ gain: g }) {
      // Hold the stage-1 bed and duck to the limbo level — in place, no restart.
      if (gameMusic.live) gameMusic.restage({ escalate: false });
      gameMusic.fadeTo(g > 0 ? g * DUCK_LEVEL : 0, FADE_MS);
    },
    gain,
    audioRunning,
    retarget(name, urls) {
      if (name === "lobby") lobbyMusic.setUrl(urls);
      else gameMusic.setUrls(urls);
    },
  };
}
