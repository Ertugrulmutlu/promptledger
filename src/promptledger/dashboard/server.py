"""Small local HTTP server for the PromptLedger dashboard."""

from __future__ import annotations

import json
import mimetypes
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from promptledger.core import PromptLedger
from . import api

STATIC_DIR = Path(__file__).resolve().parent / "static"
ALLOWED_MARKERS = {"stable", "milestone"}


def create_handler(ledger: PromptLedger | None = None):
    active_ledger = ledger or PromptLedger()

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "PromptLedgerDashboard/0.6"

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path.startswith("/api/"):
                    self._handle_api(parsed.path, parse_qs(parsed.query))
                else:
                    self._handle_static(parsed.path)
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # pragma: no cover - defensive boundary
                self._send_json({"error": f"Unexpected dashboard error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self) -> None:
            self._handle_marker_write("POST")

        def do_DELETE(self) -> None:
            self._handle_marker_write("DELETE")

        def _handle_api(self, path: str, query: dict[str, list[str]]) -> None:
            parts = [unquote(part) for part in path.strip("/").split("/")]
            if path == "/api/prompts":
                self._send_json(api.list_prompts(active_ledger))
                return
            if path == "/api/search":
                self._send_json(
                    api.search_prompts(
                        active_ledger,
                        contains=_first(query, "contains", ""),
                        collection=_first(query, "collection"),
                        role=_first(query, "role"),
                        env=_first(query, "env"),
                        tag=_first(query, "tag"),
                        marker=_first(query, "marker"),
                        label=_first(query, "label"),
                    )
                )
                return
            if path == "/api/stats":
                self._send_json(api.stats(active_ledger))
                return
            if len(parts) >= 3 and parts[0] == "api" and parts[1] == "prompts":
                prompt_id = parts[2]
                if len(parts) == 3:
                    payload = api.get_prompt(active_ledger, prompt_id)
                    self._send_json_or_404(payload)
                    return
                if len(parts) == 4 and parts[3] == "versions":
                    self._send_json(api.get_versions(active_ledger, prompt_id))
                    return
                if len(parts) == 5 and parts[3] == "versions":
                    try:
                        version = int(parts[4])
                    except ValueError:
                        self._send_json({"error": "Version must be an integer."}, HTTPStatus.BAD_REQUEST)
                        return
                    self._send_json_or_404(api.get_version(active_ledger, prompt_id, version))
                    return
            self._send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

        def _handle_marker_write(self, method: str) -> None:
            parsed = urlparse(self.path)
            parts = [unquote(part) for part in parsed.path.strip("/").split("/")]
            try:
                if (
                    len(parts) == 7
                    and parts[0] == "api"
                    and parts[1] == "prompts"
                    and parts[3] == "versions"
                    and parts[5] == "markers"
                ):
                    prompt_id = parts[2]
                    try:
                        version = int(parts[4])
                    except ValueError:
                        self._send_json({"error": "Version must be an integer."}, HTTPStatus.BAD_REQUEST)
                        return
                    marker_name = parts[6]
                    if marker_name not in ALLOWED_MARKERS:
                        self._send_json({"error": "Unsupported marker name."}, HTTPStatus.BAD_REQUEST)
                        return
                    if active_ledger.get(prompt_id, version) is None:
                        self._send_json({"error": "Prompt version not found."}, HTTPStatus.NOT_FOUND)
                        return
                    if method == "POST":
                        active_ledger.set_marker(prompt_id, version, marker_name)
                    elif method == "DELETE":
                        active_ledger.remove_marker(prompt_id, version, marker_name)
                    payload = api.get_version(active_ledger, prompt_id, version)
                    self._send_json({"ok": True, "version": payload})
                    return
                self._send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # pragma: no cover - defensive boundary
                self._send_json({"error": f"Unexpected dashboard error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def _handle_static(self, path: str) -> None:
            relative = "index.html" if path in {"/", ""} else path.lstrip("/")
            candidate = (STATIC_DIR / relative).resolve()
            if not str(candidate).startswith(str(STATIC_DIR.resolve())) or not candidate.is_file():
                self._send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
                return
            content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
            body = candidate.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json_or_404(self, payload) -> None:
            if payload is None:
                self._send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
                return
            self._send_json(payload)

        def _send_json(self, payload, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return DashboardHandler


def _first(query: dict[str, list[str]], name: str, default: str | None = None) -> str | None:
    values = query.get(name)
    if not values:
        return default
    value = values[0].strip()
    return value if value else default


def launch_dashboard(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    ledger: PromptLedger | None = None,
) -> None:
    url = f"http://{host}:{port}/"
    server = ThreadingHTTPServer((host, port), create_handler(ledger))
    print(f"PromptLedger dashboard: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPromptLedger dashboard stopped.")
    finally:
        server.server_close()
