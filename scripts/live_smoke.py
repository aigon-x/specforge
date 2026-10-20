#!/usr/bin/env python3
"""Live Nebius Token Factory smoke test with request/response/latency evidence.

This script makes one real chat-completions call using the same enrichment
prompt that ``forge --live`` sends. It records the request (authorization
redacted), the raw response, the HTTP status and the measured latency as JSON.

It refuses to run without ``NEBIUS_API_KEY``; it never writes the key.

Example:
    NEBIUS_API_KEY=... python3 scripts/live_smoke.py --out out/live_smoke.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from specforge.brief import load_brief  # noqa: E402
from specforge.enrich import build_messages, parse_payload  # noqa: E402
from specforge.errors import NebiusError, SpecForgeError  # noqa: E402
from specforge.generator import generate_spec  # noqa: E402
from specforge.nebius import DEFAULT_BASE_URL, DEFAULT_MODEL  # noqa: E402


def _build_payload(brief_path: str, model: str) -> tuple[dict[str, Any], dict[str, Any]]:
    brief = load_brief(Path(brief_path))
    spec = generate_spec(brief)
    messages = build_messages(brief, spec)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    summary = {
        "brief": str(brief_path),
        "operations": sum(
            1 for item in spec.get("paths", {}).values()
            for operation in item.values()
            if isinstance(operation, dict) and "operationId" in operation
        ),
        "requirements": len(brief.requirements),
    }
    return payload, summary


def _write(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", default=str(ROOT / "briefs" / "shop.yaml"))
    parser.add_argument("--out", default=str(ROOT / "out" / "live_smoke.json"))
    parser.add_argument("--model", default=os.environ.get("NEBIUS_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=os.environ.get("NEBIUS_API_BASE", DEFAULT_BASE_URL))
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)

    api_key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not api_key:
        print("error: NEBIUS_API_KEY is not set; live smoke test not run", file=sys.stderr)
        return 2

    try:
        payload, brief_summary = _build_payload(args.brief, args.model)
    except SpecForgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    url = args.base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(payload).encode("utf-8")
    request_record = {
        "method": "POST",
        "url": url,
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer <redacted>",
            "User-Agent": "specforge-live-smoke/1.0",
        },
        "body": payload,
    }
    record: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "nebius-token-factory",
        "model": args.model,
        "base_url": args.base_url,
        "brief": brief_summary,
        "request": request_record,
        "response": None,
        "latency_ms": None,
        "ok": False,
    }

    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "specforge-live-smoke/1.0",
        },
    )
    started = time.perf_counter()
    status = 0
    headers: dict[str, str] = {}
    raw = ""
    error = ""
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            status = response.status
            headers = dict(response.headers.items())
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        headers = dict(exc.headers.items() if exc.headers else {})
        raw = exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        error = str(exc)
    latency_ms = int((time.perf_counter() - started) * 1000)

    parsed_ok = False
    parsed_error = ""
    content = None
    if status and 200 <= status < 300:
        try:
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
            parse_payload(content)
            parsed_ok = True
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, NebiusError) as exc:
            parsed_error = f"{type(exc).__name__}: {exc}"

    record["response"] = {
        "status": status,
        "headers": headers,
        "body": raw,
        "content": content,
        "parsed_as_enrichment_json": parsed_ok,
        "parse_error": parsed_error,
    }
    record["latency_ms"] = latency_ms
    record["error"] = error
    record["ok"] = bool(status and 200 <= status < 300 and parsed_ok)
    _write(Path(args.out), record)

    print(f"model: {args.model}")
    print(f"endpoint: {url}")
    print(f"status: {status or 'no response'}")
    print(f"latency_ms: {latency_ms}")
    print(f"enrichment_json: {'valid' if parsed_ok else 'invalid'}")
    if error:
        print(f"error: {error}", file=sys.stderr)
    print(f"evidence: {args.out}")
    return 0 if record["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
