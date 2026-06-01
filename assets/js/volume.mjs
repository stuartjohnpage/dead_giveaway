// Client-side audio volume settings, persisted in localStorage and shared between
// the home page (where they're configured) and the game (where the SFX gain is
// applied). `enabled` is the master on/off switch; each channel is a 0–100 percentage
// and master scales the lot. SFX is the only channel today — music is issue #3.
// Effective gain is enabled × master × channel.

const VOL_KEY = "dg:volume";
const SLIDER_KEYS = ["master", "sfx"];
const DEFAULTS = { enabled: true, master: 100, sfx: 70 };

export function loadVolume() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(VOL_KEY) || "{}") };
  } catch {
    return { ...DEFAULTS }; // private mode / corrupt value → fall back to defaults
  }
}

export function saveVolume(volume) {
  try {
    localStorage.setItem(VOL_KEY, JSON.stringify(volume));
  } catch {
    /* storage unavailable (private mode) — settings just won't persist */
  }
}

export const sfxGain = (volume) =>
  volume.enabled ? (volume.master / 100) * (volume.sfx / 100) : 0;

// Wire the `vol-<key>` range inputs (and their `vol-<key>-val` readouts) to a volume
// object, writing changes straight back to localStorage. Inputs that aren't on the
// page are skipped, so this is safe to call wherever the controls might live. The
// optional `onChange(volume)` fires after every adjustment — e.g. to scale music that
// is already playing while the slider moves.
export function bindVolumeSliders(onChange = null, volume = loadVolume()) {
  for (const key of SLIDER_KEYS) {
    const input = document.getElementById(`vol-${key}`);
    const valOut = document.getElementById(`vol-${key}-val`);
    if (!input) continue;
    const show = () => valOut && (valOut.textContent = `${volume[key]}%`);
    input.value = String(volume[key]);
    show();
    input.addEventListener("input", () => {
      volume[key] = Number(input.value);
      show();
      saveVolume(volume);
      onChange?.(volume);
    });
  }
  return volume;
}

// Wire the sound on/off radios (`name="sound"`, values "on"/"off") to the volume's
// `enabled` flag: reflect the stored state, persist changes, show/hide the slider
// container (`#vol-sliders`), and fire `onChange(volume)`. No-op if the radios aren't
// on the page.
export function bindSoundToggle(onChange = null, volume = loadVolume()) {
  const radios = document.querySelectorAll('input[name="sound"]');
  if (!radios.length) return volume;
  const sliders = document.getElementById("vol-sliders");
  const showSliders = () => sliders && (sliders.hidden = !volume.enabled);
  for (const radio of radios) {
    radio.checked = (radio.value === "on") === volume.enabled;
    radio.addEventListener("change", () => {
      if (!radio.checked) return;
      volume.enabled = radio.value === "on";
      saveVolume(volume);
      showSliders();
      onChange?.(volume); // a radio change is a user gesture — safe to start audio here
    });
  }
  showSliders(); // reflect stored state on load only — no onChange (there's been no gesture yet)
  return volume;
}
