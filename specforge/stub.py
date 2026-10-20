"""Local HTTP stub for running generated contract tests without a network.

Routes are keyed by ``operationId`` and test case name. Generated tests send
``X-SpecForge-Operation`` and ``X-SpecForge-Case`` so the stub can return the
status and body that the spec declares for that case.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

from .contract_tests import build_test_plan, response_sample


@dataclass(frozen=True)
class StubResponse:
    status: int
    body: Any = None
    content_type: str = "application/json"


@dataclass
class StubRequest:
    method: str
    path: str
    operation: str
    case: str
    status: int


def build_stub_routes(spec: dict[str, Any]) -> dict[str, dict[str, StubResponse]]:
    """Map operationId -> case name -> the response declared by the spec."""
    operations: dict[str, dict[str, Any]] = {}
    for item in spec.get("paths", {}).values():
        if not isinstance(item, dict):
            continue
        for method, operation in item.items():
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if method.lower() in ("get", "post", "patch", "put", "delete"):
                if isinstance(operation_id, str):
                    operations[operation_id] = operation
    routes: dict[str, dict[str, StubResponse]] = {}
    for test in build_test_plan(spec):
        operation = operations.get(test["operation"], {})
        status = int(test["expect"])
        body = response_sample(spec, operation, str(status))
        response = operation.get("responses", {}).get(str(status), {})
        content = response.get("content", {}) if isinstance(response, dict) else {}
        content_type = "application/json"
        if isinstance(content, dict) and "application/problem+json" in content:
            content_type = "application/problem+json"
        routes.setdefault(test["operation"], {})[test["name"]] = StubResponse(
            status=status, body=body, content_type=content_type
        )
    return routes


class _StubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def do_PATCH(self) -> None:  # noqa: N802
        self._handle()

    def do_PUT(self) -> None:  # noqa: N802
        self._handle()

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        operation = self.headers.get("X-SpecForge-Operation", "")
        case = self.headers.get("X-SpecForge-Case", "")
        routes = self.server.routes  # type: ignore[attr-defined]
        response = routes.get(operation, {}).get(case)
        if response is None:
            response = StubResponse(
                status=404,
                body={
                    "type": "about:blank",
                    "title": "Unknown stub case",
                    "status": 404,
                    "detail": f"{self.command} {self.path} {operation!r} {case!r}",
                },
                content_type="application/problem+json",
            )
        payload = b""
        if response.body is not None:
            payload = json.dumps(response.body).encode("utf-8")
        records = self.server.records  # type: ignore[attr-defined]
        records.append(StubRequest(
            method=self.command,
            path=self.path,
            operation=operation,
            case=case,
            status=response.status,
        ))
        self.send_response(response.status)
        if payload:
            self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)


@dataclass
class StubServer:
    base_url: str
    routes: dict[str, dict[str, StubResponse]]
    records: list[StubRequest] = field(default_factory=list)


@contextmanager
def stub_server(routes: dict[str, dict[str, StubResponse]]) -> Iterator[StubServer]:
    """Start the stub on a loopback port and stop it afterwards."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    httpd.routes = routes  # type: ignore[attr-defined]
    httpd.records = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    handle = StubServer(
        base_url=f"http://127.0.0.1:{httpd.server_address[1]}",
        routes=routes,
        records=httpd.records,  # type: ignore[attr-defined]
    )
    try:
        yield handle
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
