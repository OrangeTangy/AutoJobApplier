"""
Desktop launcher for AutoJobApplier.

This is the PyInstaller entry point: it starts the embedded FastAPI server,
ensures Playwright's Chromium binary is installed, opens the user's default
browser to the app, and shows a system-tray icon for clean shutdown.

Runs as a single double-clickable executable — no Docker, no terminal, no
localhost URLs to memorize.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# ── Resolve runtime directories before importing the app ─────────────────────
# When frozen (PyInstaller), sys._MEIPASS points at the extracted bundle.
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
os.environ.setdefault("PYTHONUNBUFFERED", "1")

# Persist Playwright browsers alongside the user's app data so we don't
# re-download them on every launch.
if sys.platform == "win32":
    _appdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
elif sys.platform == "darwin":
    _appdata = Path.home() / "Library" / "Application Support"
else:
    _appdata = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
APP_DATA = _appdata / "AutoJobApplier"
APP_DATA.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("AUTOJOB_DATA_DIR", str(APP_DATA))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(APP_DATA / "playwright"))
os.environ.setdefault("FRONTEND_DIST_DIR", str(BUNDLE_DIR / "frontend_dist"))

# ── Imports that depend on the env vars above ───────────────────────────────
import uvicorn  # noqa: E402


def _pick_free_port(preferred: int = 8765) -> int:
    """Return `preferred` if available, otherwise any free port."""
    for candidate in (preferred, 0):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", candidate))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            continue
    return preferred


def _install_playwright_browsers() -> None:
    """Run `playwright install chromium` on first launch. Idempotent."""
    marker = APP_DATA / ".playwright-installed"
    if marker.exists():
        return
    try:
        import subprocess

        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=False,
            capture_output=True,
        )
        marker.write_text("ok")
    except Exception as exc:  # pragma: no cover
        print(f"[launcher] Playwright install skipped: {exc}", file=sys.stderr)


def _open_browser_when_ready(url: str, *, timeout: float = 20.0) -> None:
    """Poll the health endpoint, then open the user's default browser."""
    deadline = time.monotonic() + timeout
    health = f"{url}/api/health"
    import urllib.error
    import urllib.request

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health, timeout=1.0) as resp:
                if resp.status == 200:
                    break
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.25)
    webbrowser.open(url, new=1, autoraise=True)


def _run_server(host: str, port: int) -> None:
    """Start uvicorn in-process. Blocks until the server exits."""
    # Import here so PyInstaller's dependency scan picks up the graph.
    from app.main import app as fastapi_app

    config = uvicorn.Config(
        fastapi_app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
        workers=1,
    )
    server = uvicorn.Server(config)
    server.run()


def _run_tray(url: str, stop: threading.Event) -> None:
    """Show a system-tray icon with a 'Quit' menu item.

    If `pystray`/Pillow aren't available (headless CI, minimal install),
    fall back to printing the URL and waiting for Ctrl+C.
    """
    try:
        from PIL import Image, ImageDraw
        from pystray import Icon, Menu, MenuItem
    except Exception:
        print(f"AutoJobApplier running at {url}")
        print("Press Ctrl+C to quit.")
        try:
            while not stop.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            stop.set()
        return

    # 64×64 circular icon drawn at runtime (avoids shipping PNG assets).
    img = Image.new("RGB", (64, 64), color=(16, 24, 48))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, 56, 56), fill=(96, 165, 250))
    draw.text((22, 20), "AJ", fill=(255, 255, 255))

    def _open(_icon=None, _item=None):
        webbrowser.open(url, new=1, autoraise=True)

    def _quit(icon, _item=None):
        stop.set()
        icon.stop()

    icon = Icon(
        "AutoJobApplier",
        img,
        "AutoJobApplier",
        menu=Menu(
            MenuItem("Open App", _open, default=True),
            MenuItem("Quit", _quit),
        ),
    )
    icon.run()


def main() -> int:
    host = "127.0.0.1"
    port = _pick_free_port(int(os.environ.get("AUTOJOB_PORT", "8765")))
    url = f"http://{host}:{port}"

    _install_playwright_browsers()

    stop = threading.Event()
    server_thread = threading.Thread(
        target=_run_server, args=(host, port), name="uvicorn", daemon=True
    )
    server_thread.start()

    browser_thread = threading.Thread(
        target=_open_browser_when_ready, args=(url,), daemon=True
    )
    browser_thread.start()

    try:
        _run_tray(url, stop)
    finally:
        stop.set()
        # Give uvicorn a moment to finish outstanding requests.
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
