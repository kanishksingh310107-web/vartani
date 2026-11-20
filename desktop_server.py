"""Serve the desktop window on a private loopback listener."""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading

from launcher import bundle_root, ensure_bundle, ensure_profile, resolve_profile_paths, _server_config


def main() -> int:
    # Windows supplies redirected pipes when Vartani.exe starts this worker.
    paths = resolve_profile_paths()
    ensure_bundle(bundle_root())
    ensure_profile(paths)
    os.environ["VARTANI_HOME"] = str(paths.home)
    os.environ["VARTANI_DATA"] = str(paths.data)
    logging.basicConfig(filename=paths.logs / "desktop.log", encoding="utf-8", level=logging.WARNING)

    from starlette.middleware.trustedhost import TrustedHostMiddleware
    import uvicorn
    from vartani.app import app

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1"])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        class DesktopServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                if self.started:
                    print(f"READY {port}", flush=True)

        server = DesktopServer(_server_config(app, "127.0.0.1", port))

        def stop_when_window_closes():
            # EOF even if the parent is killed. No shutdown endpoint exposed.
            sys.stdin.buffer.read()
            server.should_exit = True

        threading.Thread(target=stop_when_window_closes, daemon=True).start()
        server.run(sockets=[listener])
        return 0 if server.started else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from None
