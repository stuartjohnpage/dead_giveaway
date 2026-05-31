// Pure coordinate transforms between the server's world space and screen pixels.
//
// World space matches the authoritative sim: x runs along the track [0, worldW],
// y is row * row_spacing [0, worldH]. Screen space is a padded box so sprites
// never clip the canvas edge. Kept Pixi-free so it can be unit-tested directly.

export function worldToScreen(wx, wy, view) {
  const { worldW, worldH, screenW, screenH, pad = 0 } = view;
  return {
    sx: pad + (wx / worldW) * (screenW - 2 * pad),
    sy: pad + (wy / worldH) * (screenH - 2 * pad),
  };
}

export function screenToWorld(sx, sy, view) {
  const { worldW, worldH, screenW, screenH, pad = 0 } = view;
  return {
    wx: ((sx - pad) / (screenW - 2 * pad)) * worldW,
    wy: ((sy - pad) / (screenH - 2 * pad)) * worldH,
  };
}
