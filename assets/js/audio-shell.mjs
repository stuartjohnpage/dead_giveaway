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
import { createMusicLoop, createEscalatingLoop, audioRunning, MUSIC_GAIN, FADE_MS } from "./music.mjs";
import { createMusicDirector, createAudioPort } from "./music-director.mjs";

// The default theme's audio, used until a room's own theme is loaded — and as the
// fallback when a pack's manifest omits its tracks. Exported so game.mjs's loadTheme()
// uses the same defaults rather than redefining them.
const DEFAULT_THEME = "neon";
export const DEFAULT_MENU_LOOP = `/themes/${DEFAULT_THEME}/menu_loop.mp3`;
export const DEFAULT_GAME_STAGES = [1, 2, 3, 4].map(
  (i) => `/themes/${DEFAULT_THEME}/game/stage${i}.mp3`,
);
// The firing SFX for packs that don't declare their own (#48) — the theme-agnostic
// /sounds clip, so a shot always has a sound even with every theme folder empty.
export const DEFAULT_SHOT = "/sounds/gunshot.mp3";
// The Red Light watcher's wind-up cue (#53) falls back to the default theme's, same
// rule as the music stages — the light must be audible without watching the line.
export const DEFAULT_WINDUP = `/themes/${DEFAULT_THEME}/windup.mp3`;

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
 *   setShotUrl(url: string): void,
 *   playWindup(): void,
 *   setWindupUrl(url: string): void,
 *   armUnlock(): void,
 *   enterMenu(): void,
 *   resumeMusic(): void,
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

  // Re-gain the loop the player is actually hearing to the current volume, WITHOUT
  // restarting it — for a slider drag while music plays. Only the active loop is touched:
  // the backgrounded loop sits ducked to silence (a crossfade leaves it live but at 0), and
  // re-leveling it would bring it back over the foreground track.
  const applyMusicGain = () => {
    (music.inGame ? gameMusic : lobbyMusic).setGain(musicGain());
  };

  // A retargetable one-shot SFX slot — preloaded so the first play isn't silent while
  // the asset decodes, re-preloading the same way when a theme swap repoints it, and
  // cloned per play so overlapping plays don't cut each other off. play() swallows the
  // autoplay rejection before the first gesture; in-game the click IS the gesture.
  const createOneShot = (defaultUrl) => {
    let sfx = new Audio(defaultUrl);
    sfx.preload = "auto";
    let current = defaultUrl;
    return {
      setUrl(url) {
        if (url === current) return; // recurring lobby broadcasts — don't re-fetch
        current = url;
        sfx = new Audio(url);
        sfx.preload = "auto";
      },
      play() {
        const s = sfx.cloneNode();
        s.volume = sfxGain(volume);
        s.play().catch(() => {});
      },
    };
  };

  // Firing SFX, per-theme (#48): loadTheme retargets it, mirroring how the music loops
  // are repointed; packs without a shot stay on DEFAULT_SHOT (Pixabay, credited in
  // sounds/CREDITS.md). The wind-up cue (#53) is the Red Light watcher's audible
  // warning, retargeted the same way.
  const shot = createOneShot(DEFAULT_SHOT);
  const windup = createOneShot(DEFAULT_WINDUP);

  // Return to the splash/menu from anywhere — the home page calls this on mount, which
  // (post client-side nav) may be arriving back from a live game. Reset the director to the
  // lobby view, then make the menu loop the one we hear.
  //
  // On a fresh load (context suspended) or with sound off, leave first playback to the home
  // gesture and just make sure a left-over game loop isn't sounding. Otherwise (unlocked +
  // sound on): if the menu loop is already up — carried over from a pre-round lobby — keep
  // it (seamless, no restart); if it's backgrounded under a game (ducked to silence by the
  // lobby→round crossfade) fade it back up; if it never started, start it with a fade-in.
  // Either way crossfade the game loop out. `wanted` (not just `live`) covers a menu loop
  // whose start() is still decoding, so we never stack a second start on top of it.
  const enterMenu = () => {
    music.adoptLobby();
    if (!volume.enabled || !audioRunning()) {
      if (!lobbyMusic.wanted && !lobbyMusic.live) gameMusic.stop();
      return;
    }
    if (lobbyMusic.live) lobbyMusic.fadeTo(musicGain(), FADE_MS);
    else if (!lobbyMusic.wanted) lobbyMusic.start(musicGain(), { fadeMs: FADE_MS });
    if (gameMusic.live) gameMusic.fadeTo(0, FADE_MS);
  };

  // Make sure the current view's loop is actually playing — for when sound is switched ON
  // from the gear. Because muting ducks gain rather than stopping, a loop that has ever
  // played stays live, so this only kicks in for a loop that was never started (the page
  // was loaded with sound off). Picks the loop by the director's current view.
  const resumeMusic = () => {
    const current = music.inGame ? gameMusic : lobbyMusic;
    if (current.live) return;
    if (music.inGame) music.toRound();
    else music.toLobby();
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

  return {
    music,
    lobbyMusic,
    gameMusic,
    volume,
    musicGain,
    applyMusicGain,
    playShot: shot.play,
    setShotUrl: shot.setUrl,
    playWindup: windup.play,
    setWindupUrl: windup.setUrl,
    armUnlock,
    enterMenu,
    resumeMusic,
  };
}
