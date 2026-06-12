// If you want to use Phoenix channels, run `mix help phx.gen.channel`
// to get started and then uncomment the line below.
// import "./user_socket.js"

// You can include dependencies in two ways.
//
// The simplest option is to put them in assets/vendor and
// import them using relative paths:
//
//     import "../vendor/some-package.js"
//
// Alternatively, you can `npm install some-package --prefix assets` and import
// them using a path starting with the package name:
//
//     import "some-package"
//
// If you have dependencies that try to import CSS, esbuild will generate a separate `app.css` file.
// To load it, simply add a second `<link>` to your `root.html.heex` file.

// Include phoenix_html to handle method=PUT/DELETE in forms and buttons.
import "phoenix_html"
// Establish Phoenix Socket and LiveView configuration.
// import {Socket} from "phoenix"
// import {LiveSocket} from "phoenix_live_view"
// import {hooks as colocatedHooks} from "phoenix-colocated/dead_giveaway"
// import topbar from "../vendor/topbar"

// const csrfToken = document.querySelector("meta[name='csrf-token']").getAttribute("content")
// const liveSocket = new LiveSocket("/live", Socket, {
//   longPollFallbackMs: 2500,
//   params: {_csrf_token: csrfToken},
//   hooks: {...colocatedHooks},
// })

// Show progress bar on live navigation and form submits
// topbar.config({barColors: {0: "#29d"}, shadowColor: "rgba(0, 0, 0, .3)"})
// window.addEventListener("phx:page-loading-start", _info => topbar.show(300))
// window.addEventListener("phx:page-loading-stop", _info => topbar.hide())

// connect if there are any LiveViews on the page
// liveSocket.connect()

// expose liveSocket on window for web console debug logs and latency simulation:
// >> liveSocket.enableDebug()
// >> liveSocket.enableLatencySim(1000)  // enabled for duration of browser session
// >> liveSocket.disableLatencySim()
// window.liveSocket = liveSocket

// The lines below enable quality of life phoenix_live_reload
// development features:
//
//     1. stream server logs to the browser console
//     2. click on elements to jump to their definitions in your code editor
//
// if (process.env.NODE_ENV === "development") {
//   window.addEventListener("phx:live_reload:attached", ({detail: reloader}) => {
//     // Enable server log streaming to client.
//     // Disable with reloader.disableServerLogs()
//     reloader.enableServerLogs()
// 
//     // Open configured PLUG_EDITOR at file:line of the clicked element's HEEx component
//     //
//     //   * click with "c" key pressed to open at caller location
//     //   * click with "d" key pressed to open at function component definition location
//     let keyDown
//     window.addEventListener("keydown", e => keyDown = e.key)
//     window.addEventListener("keyup", _e => keyDown = null)
//     window.addEventListener("click", e => {
//       if(keyDown === "c"){
//         e.preventDefault()
//         e.stopImmediatePropagation()
//         reloader.openEditorAtCaller(e.target)
//       } else if(keyDown === "d"){
//         e.preventDefault()
//         e.stopImmediatePropagation()
//         reloader.openEditorAtDef(e.target)
//       }
//     }, true)
// 
//     window.liveReloader = reloader
//   })
// }


import { boot } from "./game.mjs"
import { getAudio } from "./audio-shell.mjs"
import { bindVolumeSliders, bindSoundToggle } from "./volume.mjs"
import { initRouter } from "./router.mjs"
import { mountOpenLobbies } from "./lobbies.mjs"
import { mountIdentity } from "./identity.mjs"
import { mountSpritePicker } from "./sprite-picker.mjs"

// Mount the current page in place. Called once for the server-rendered page at load and
// again by the router after each client-side content swap, so all per-page setup must be
// re-runnable here (top-level init wouldn't run after a swap). Returns a teardown the
// router calls before navigating away, or nothing for a page that needs no cleanup.
async function mount() {
  // Flash banners — re-bound each page (their elements are replaced on every swap).
  document.querySelectorAll("[role=alert][data-flash]").forEach((el) => {
    el.addEventListener("click", () => el.setAttribute("hidden", ""))
  })

  // The audio-settings gear lives in the root layout, so it's on every page — wire it
  // (and its controls) to the shared shell each mount.
  mountAudioSettings()

  // The game page mounts the Pixi/socket client (and owns its own audio playback).
  if (document.getElementById("game")) return boot()

  // The home splash plays the menu music; the gear above controls its volume. Returns a
  // teardown (the open-lobbies channel) the router runs before navigating into a game.
  if (document.getElementById("create-form")) return mountHome()
}

// Wire the always-accessible audio gear (#19): toggle the panel, and bind its On/Off +
// sliders to the shared audio shell so a change takes effect live on any screen — the
// sliders re-gain whatever loop is playing, and the On/Off ducks/boosts it (muting is a
// gain-0 duck, not a stop). Present on every page (root layout), so this runs each mount;
// its listeners are all on swapped-away DOM, so there's nothing to tear down.
function mountAudioSettings() {
  const gear = document.getElementById("audio-gear")
  const panel = document.getElementById("audio-panel")
  if (!gear || !panel) return

  gear.addEventListener("click", () => (panel.hidden = !panel.hidden))

  const { volume, applyMusicGain, resumeMusic, playShot } = getAudio()
  bindSoundToggle((v) => {
    applyMusicGain() // duck to silence when off, or restore the live loop's level when on
    if (v.enabled) resumeMusic() // and start the current view's loop if it never began
  }, volume)
  bindVolumeSliders(() => applyMusicGain(), volume)

  // Preview the firing SFX at the chosen level on slider release (change, not input, so
  // it's one shot per adjustment). playShot reads the current sfx gain (0 when off).
  document.getElementById("vol-sfx")?.addEventListener("change", () => playShot())
}

// Home splash: put the director in the menu/lobby view so the menu loop plays, and arm
// the autoplay unlock so it sounds on the first gesture (the same path boot() uses for the
// game). enterMenu adopts an already-playing loop without a restart, so arriving here from
// a lobby is seamless, and resets off a left-over game loop otherwise (#20).
function mountHome() {
  const audio = getAudio()
  audio.enterMenu()
  audio.armUnlock()
  // Hydrate the name field from the remembered value and keep it in sync as the user types,
  // so the chosen name persists across visits and rides every join (#43 follow-up).
  mountIdentity()
  // The sprite picker on the identity card (#67) — remembered and carried the same way.
  mountSpritePicker()
  // Live "open lobbies" list (#43); returns a teardown that drops its socket on navigate.
  return mountOpenLobbies()
}

// Take over the home↔play navigations (and mount the initial page). Everything degrades to
// ordinary full-page loads if JS is off or this throws (the forms/links keep working).
initRouter(mount)