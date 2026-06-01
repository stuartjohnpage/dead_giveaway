// Pure coordinate transforms between the server's world space and screen pixels.
//
// World space matches the authoritative sim: x runs along the track [0, worldW],
// y is row * row_spacing [0, worldH]. Screen space is a padded box so sprites
// never clip the canvas edge. Kept Pixi-free so it can be unit-tested directly.
//
// `pad` insets both axes equally; `padX`/`padY` override per-axis (defaulting to
// `pad`) — the arena confines runners to the floor band vertically (a large padY)
// while keeping the track full-width horizontally (a small padX).

export function worldToScreen(wx, wy, view) {
  const { worldW, worldH, screenW, screenH, pad = 0, padX = pad, padY = pad } = view;
  return {
    sx: padX + (wx / worldW) * (screenW - 2 * padX),
    sy: padY + (wy / worldH) * (screenH - 2 * padY),
  };
}

export function screenToWorld(sx, sy, view) {
  const { worldW, worldH, screenW, screenH, pad = 0, padX = pad, padY = pad } = view;
  return {
    wx: ((sx - padX) / (screenW - 2 * padX)) * worldW,
    wy: ((sy - padY) / (screenH - 2 * padY)) * worldH,
  };
}
