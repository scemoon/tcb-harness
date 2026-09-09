"""Trace dashboard — built-in web UI with Chart.js, no npm needed.

Usage:
    from cdh.trace.dashboard import run_dashboard
    run_dashboard(port=5173)
"""

from __future__ import annotations

import os
import webbrowser
from pathlib import Path

from cdh.trace import get_db_path


def _load_app_html() -> str:
    """Load the frontend HTML from the app.html file in this package."""
    pkg_dir = Path(__file__).resolve().parent
    html_path = pkg_dir / "app.html"
    return html_path.read_text(encoding="utf-8")


def run_dashboard(port: int = 5173, host: str = "127.0.0.1") -> None:
    """Start the trace dashboard web server.

    Args:
        port: HTTP port (default 5173).
        host: Bind address (default 127.0.0.1).
    """
    db_path = get_db_path()
    app_html = _load_app_html()

    print(f"Trace DB: {db_path}")
    print("")
    print(f"Starting CDH Trace Dashboard at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    print("")

    from cdh.trace.dashboard.server import make_server

    server = make_server(host, port, app_html, db_path)

    # Don't open browser in headless/CI environments
    _try_open_browser = True
    display = os.environ.get("DISPLAY")
    if display is not None and not display:
        _try_open_browser = False
    if "DISPLAY" not in os.environ:
        _try_open_browser = False
    if _try_open_browser:
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()
