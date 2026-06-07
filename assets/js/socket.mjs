// Shared websocket bring-up. Both the game (room:CODE) and the home directory ("lobbies")
// open a Phoenix socket + channel the same way and tear it down on navigate, so that dance
// lives here once instead of being copy-pasted into each module.

import { Socket } from "phoenix";

// Connect a socket, open `topic` with `params`, and return the channel plus a teardown that
// leaves the channel and drops the socket. The caller still drives channel.join()/.on(...) —
// this only owns the connect + the symmetric close.
export function openChannel(topic, params = {}) {
  const socket = new Socket("/socket", {});
  socket.connect();
  const channel = socket.channel(topic, params);

  // leave and disconnect are independently best-effort: a half-open socket shouldn't let one
  // failure skip the other, and tearing down twice (or after the server already dropped us)
  // must never throw.
  const teardown = () => {
    try {
      channel.leave();
    } catch {
      /* already gone */
    }
    try {
      socket.disconnect();
    } catch {
      /* already gone */
    }
  };

  return { socket, channel, teardown };
}
