"""Trace dashboard HTTP server — routes requests to API handlers."""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cdh.trace.dashboard.api import (
    export_traces,
    get_agents,
    get_cost_stats,
    get_env_stats,
    get_error_stats,
    get_latency_stats,
    get_loc_stats,
    get_model_stats,
    get_overview,
    get_scatter_data,
    get_session_detail,
    get_sessions,
    get_tag_stats,
    get_tool_stats,
    get_traces,
    get_user_stats,
)


_FAVICON = (
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAA"
    "bAAAAbABwgXCIwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAAEkSURBVDiNpZOx"
    "SgNBEIb/r7lLDJpGJFY2dhZifAGfwCfwEXwDC8FPEEEEGxvBws4uKlrYKYKFqI0WSpJY7M3uWDh3e0oS"
    "YZBlh/nZmf9fdoQxxsPvByKiePAZEY0xx3Vdr8YY/Q+QmT3P84wx+BMBAGMMi8UCAJCmqel0OgCAVqsF"
    "AMD9/X0l2Pd9lMtl1Go1TCaTny+ZTAZ5nofNZgPGGJIkQRAE6Pf7YIyh3+/j8fERWZah1+t9E3HOsfF8"
    "PkepVMJ0OsVoNEKpVAIRoV6v4/z8HGEYotlsYjqdQkTAGEMul0MikYCqKiiKIkR0J0TUExEQAOacAwAa"
    "jQZ2ux0A4OjoCJvNBgBQLpcRBAFE5E0E55wDABhjyLJsfw/7l4gAETljjImI5Jx7ExH5A36NAyI6FxFd"
    "ENGpiDyKyAsRnb4DEDy/AwN0wMYAAAAASUVORK5CYII="
)


class _DashboardHandler(SimpleHTTPRequestHandler):
    """Request handler that routes paths to API endpoints or serves the HTML app."""

    def __init__(self, *args: Any, app_html: str = "", db_path: Path | None = None, **kwargs: Any):
        self._app_html = app_html
        self._db_path = db_path
        super().__init__(*args, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = dict(urllib.parse.parse_qsl(parsed.query))

        routes: dict[str, Any] = {
            "/": self._send_html,
            "/api/overview": self._api_overview,
            "/api/traces": self._api_traces,
            "/api/sessions": self._api_sessions,
            "/api/agents": self._api_agents,
            "/api/stats/models": self._api_models,
            "/api/stats/tools": self._api_tools,
            "/api/stats/errors": self._api_errors,
            "/api/stats/cost": self._api_cost,
            "/api/stats/loc": self._api_loc,
            "/api/stats/latency": self._api_latency,
            "/api/stats/scatter": self._api_scatter,
            "/api/stats/users": self._api_users,
            "/api/stats/tags": self._api_tags,
            "/api/stats/environments": self._api_envs,
            "/api/export": self._api_export,
        }

        # Match /api/sessions/<id>
        session_detail_match = re.match(r"^/api/sessions/(.+)$", path)
        if session_detail_match:
            self._api_session_detail(session_detail_match.group(1))
            return

        handler = routes.get(path)
        if handler:
            handler(params if path != "/" else None)
        elif path == "/favicon.ico":
            self._send_favicon()
        elif not path.startswith("/api/"):
            self._send_html()
        else:
            self.send_json({"status": "error", "error": "not found"}, 404)

    def _send_html(self, _params: dict | None = None):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(self._app_html.encode("utf-8"))

    def _send_favicon(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(base64.b64decode(_FAVICON))

    def send_json(self, data: Any, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _api_overview(self, params: dict):
        try:
            data = get_overview(self._db_path, start=params.get("start"), end=params.get("end"))
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_traces(self, params: dict):
        try:
            data = get_traces(
                self._db_path,
                limit=int(params.get("limit", 50)),
                offset=int(params.get("offset", 0)),
                trace_type=params.get("type"),
                agent=params.get("agent"),
                model=params.get("model"),
                status=params.get("status"),
                session_id=params.get("session_id"),
                search=params.get("search"),
                start=params.get("start"),
                end=params.get("end"),
            )
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_sessions(self, params: dict):
        try:
            data = get_sessions(
                self._db_path,
                limit=int(params.get("limit", 100)),
                offset=int(params.get("offset", 0)),
            )
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_session_detail(self, session_id: str):
        try:
            data = get_session_detail(self._db_path, session_id)
            if data is None:
                self.send_json({"status": "error", "error": "session not found"}, 404)
            else:
                self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_agents(self, _params: dict):
        try:
            data = get_agents(self._db_path)
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_models(self, _params: dict):
        try:
            data = get_model_stats(self._db_path)
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_tools(self, _params: dict):
        try:
            data = get_tool_stats(self._db_path)
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_errors(self, _params: dict):
        try:
            data = get_error_stats(self._db_path)
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_cost(self, params: dict):
        try:
            prices_raw = params.get("prices", "{}")
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else {}
            data = get_cost_stats(self._db_path, prices)
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_loc(self, _params: dict):
        try:
            data = get_loc_stats(self._db_path)
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_latency(self, _params: dict):
        try:
            data = get_latency_stats(self._db_path)
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_scatter(self, params: dict):
        try:
            limit = int(params.get("limit", 500))
            data = get_scatter_data(self._db_path, limit)
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_users(self, _params: dict):
        try:
            data = get_user_stats(self._db_path)
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_tags(self, _params: dict):
        try:
            data = get_tag_stats(self._db_path)
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_envs(self, _params: dict):
        try:
            data = get_env_stats(self._db_path)
            self.send_json({"status": "ok", "data": data})
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def _api_export(self, params: dict):
        try:
            fmt = params.get("format", "json")
            data = export_traces(
                self._db_path,
                fmt=fmt,
                trace_type=params.get("type"),
                agent=params.get("agent"),
                session_id=params.get("session_id"),
                limit=int(params.get("limit", 500)),
            )
            if fmt == "json":
                self.send_json(data)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", "attachment; filename=traces.csv")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(data.encode("utf-8"))
        except OSError:
            pass
        except Exception as e:
            self.send_json({"status": "error", "error": str(e)}, 500)

    def log_message(self, fmt: str, *args: Any):
        pass


def make_server(
    host: str,
    port: int,
    app_html: str,
    db_path: Path,
) -> HTTPServer:
    handler = lambda *args, **kwargs: _DashboardHandler(
        *args, app_html=app_html, db_path=db_path, **kwargs
    )
    return HTTPServer((host, port), handler)
