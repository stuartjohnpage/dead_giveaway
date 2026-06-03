// The client's persistent audio: the two background loops, the music director that
// decides which one plays (lobby vs the escalating game track), the firing SFX, and the
// shared volume level. Everything WebAudio-adjacent that used to be built inside
// game.mjs's boot() (and a parallel, separate menu loop in app.js) lives here instead.
//
// It's a module-scope singleton (getAudio()): a page owns exactly one of each, and the
// home splash and the in-game client drive that same instance. Today each full page load
// recreates it (the module reloads), so this is purely a consolidation. Once the
// home↔play hop is client-side (no document reload), the singleton — and its
// still-playing loop — will carry across seamlessly, which is the point (#20).

import { loadVolume, sfxGain } from "./volume.mjs";
import { createMusicLoop, createEscalatingLoop, audioRunning, MUSIC_GAIN } from "./music.mjs";
import { createMusicDirector, createAudioPort } from "./music-director.mjs";

// The default theme's audio, used until a room's own theme is loaded — and as the
// fallback when a pack's manifest omits its tracks. Exported so game.mjs's loadTheme()
// uses the same defaults rather than redefining them.
const DEFAULT_THEME = "neon";
export const DEFAULT_MENU_LOOP = `/themes/${DEFAULT_THEME}/menu_loop.mp3`;
export const DEFAULT_GAME_STAGES = [1, 2, 3, 4].map(
  (i) => `/themes/${DEFAULT_THEME}/game/stage${i}.mp3`,
);

let shell = null;

/**
 * The shared audio shell, created once per page (and, post client-side nav, once per
 * session). Returns the same instance on every call.
 *
 * @returns {{
 *   music: ReturnType<typeof createMusicDirector>,
 *   lobbyMusic: ReturnType<typeof createMusicLoop>,
 *   gameMusic: ReturnType<typeof createEscalatingLoop>,
 *   volume: {enabled: boolean, master: number, sfx: number},
 *   musicGain(): number,
 *   applyMusicGain(): void,
 *   playShot(): void,
 *   armUnlock(): void,
 * }}
 */
export function getAudio() {
  return (shell ||= create());
}

function create() {
  // Shared, mutable volume (sessionStorage-backed via volume.mjs). The home sound card
  // and the in-game gear both mutate this one object; gain is read fresh per transition
  // so a level change always lands.
  const volume = loadVolume();

  // The two loops: the menu/lobby loop and the four-stage escalating in-game loop. Both
  // are retargeted per theme by game.mjs's loadTheme (setUrl/setUrls); they start on the
  // default theme's tracks. master × MUSIC_GAIN, zero when sound is off.
  const lobbyMusic = createMusicLoop(DEFAULT_MENU_LOOP);
  const gameMusic = createEscalatingLoop(DEFAULT_GAME_STAGES);
  const musicGain = () => (volume.enabled ? (volume.master / 100) * MUSIC_GAIN : 0);

  // All view-transition policy (which loop, when to replay, the prime-once/suspended-only
  // unlock) lives in the director, driving the loops through the production AudioPort
  // adapter (start-one-stops-the-other, stay-silent-when-muted).
  const music = createMusicDirector(
    createAudioPort({ lobbyMusic, gameMusic, audioRunning, gain: musicGain }),
  );

  // Re-gain whichever loops are live to the current volume, WITHOUT restarting them — for
  // a slider drag while music plays. setGain on a stopped loop is a harmless no-op.
  const applyMusicGain = () => {
    lobbyMusic.setGain(musicGain());
    gameMusic.setGain(musicGain());
  };

  // Firing SFX — preloaded so the first shot isn't silent while the asset decodes.
  // Pixabay Content License, credited in priv/static/sounds/CREDITS.md. cloneNode lets
  // overlapping shots both play (the server broadcasts every peer's fire).
  const shotSfx = new Audio("/sounds/gunshot.mp3");
  shotSfx.preload = "auto";
  const playShot = () => {
    const s = shotSfx.cloneNode();
    s.volume = sfxGain(volume);
    s.play().catch(() => {}); // autoplay is rejected until the first gesture; in-game the click is the gesture
  };

  // Arm the autoplay unlock for the director: the first user gesture (of either type)
  // primes the AudioContext, replaying the queued loop only if it's still suspended, then
  // tears both listeners down. The game arms this; the home splash drives the loop
  // directly (its sound toggle is itself a gesture), so it doesn't.
  let armed = false;
  const armUnlock = () => {
    if (armed) return;
    armed = true;
    const unlock = () => {
      if (music.prime()) {
        window.removeEventListener("pointerdown", unlock);
        window.removeEventListener("keydown", unlock);
      }
    };
    window.addEventListener("pointerdown", unlock);
    window.addEventListener("keydown", unlock);
  };

  return { music, lobbyMusic, gameMusic, volume, musicGain, applyMusicGain, playShot, armUnlock };
}
