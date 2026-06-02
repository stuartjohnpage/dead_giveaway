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


// Handle flash close
document.querySelectorAll("[role=alert][data-flash]").forEach((el) => {
  el.addEventListener("click", () => {
    el.setAttribute("hidden", "")
  })
})

// Boot the Dead Giveaway client on the game page (identified by the #game element).
import { boot } from "./game.mjs"
if (document.getElementById("game")) {
  boot()
}

// Home page: bind the volume sliders (the game reads the persisted level at boot, so
// changing it here carries into play) and loop the menu's background music.
import { bindVolumeSliders, bindSoundToggle, loadVolume, sfxGain } from "./volume.mjs"
import { createMusicLoop, MUSIC_GAIN } from "./music.mjs"
if (document.getElementById("vol-master")) {
  const volume = loadVolume()
  const music = createMusicLoop("/sounds/music/neon_loop.mp3")
  // enabled × master scales the music (no dedicated music channel yet).
  const musicVol = (v) => (v.enabled ? (v.master / 100) * MUSIC_GAIN : 0)
  // The On/Off switch starts or stops the loop (flipping it is a user gesture, so
  // autoplay is allowed); the sliders only re-gain the already-playing loop — they must
  // not restart it from the top on every drag.
  bindSoundToggle((v) => (v.enabled ? music.start(musicVol(v)) : music.stop()), volume)
  bindVolumeSliders((v) => music.setGain(musicVol(v)), volume)

  // Preview the firing SFX at the chosen level so the user hears what they've set. On
  // "change" (slider release), not "input", so it's one shot per adjustment rather than
  // a machine-gun while dragging. (sfxGain is 0 when sound is off.)
  const sfxPreview = new Audio("/sounds/gunshot.mp3")
  sfxPreview.preload = "auto"
  document.getElementById("vol-sfx")?.addEventListener("change", () => {
    sfxPreview.currentTime = 0
    sfxPreview.volume = sfxGain(volume) // master × sfx — matches in-game gain
    sfxPreview.play().catch(() => {})
  })

  // If sound was left On from a previous visit, autoplay policy still needs a gesture
  // before the loop can sound — kick it off on the first interaction. (A fresh visit
  // starts Off, so this is a no-op until the player flips the switch above.)
  //
  // This must fire EXACTLY ONCE across both gesture types: start() is async (fetch +
  // decode), so music.live stays false during the decode. Clicking into the lobby-code
  // field (pointerdown) starts the load; the first keystroke (keydown) would then see
  // live still false and call start() a second time — restarting the track. So one guard
  // removes both listeners on the first gesture, rather than two independent `once`s.
  let started = false
  const startMusic = () => {
    if (started) return
    started = true
    window.removeEventListener("pointerdown", startMusic)
    window.removeEventListener("keydown", startMusic)
    if (volume.enabled && !music.live) music.start(musicVol(volume))
  }
  window.addEventListener("pointerdown", startMusic)
  window.addEventListener("keydown", startMusic)
}