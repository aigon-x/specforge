"""Deterministic enrichment payload derived from the brief itself.

Offline mode must not depend on a fixture written for one sample brief. The
payload is computed from the operations and requirements that were sent to the
model, so every brief gets prose for exactly its own operations.
"""

from __future__ import annotations

import json
from typing import Any

from .errors import FixtureError


def _user_payload(messages: list[dict[str, str]]) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        try:
            payload = json.loads(message.get("content", ""))
        except (TypeError, json.JSONDecodeError) as exc:
            raise FixtureError(
                f"offline fixture cannot read the user payload: {exc}", kind="fixture"
            ) from exc
        if not isinstance(payload, dict):
            raise FixtureError("offline fixture user payload must be an object",
                               kind="fixture")
        return payload
    raise FixtureError("offline fixture needs a user message", kind="fixture")


def build_enrichment_fixture(messages: list[dict[str, str]]) -> dict[str, Any]:
    """Build a deterministic response covering every operation in the prompt."""
    payload = _user_payload(messages)
    operations = payload.get("operations")
    requirements = payload.get("requirements")
    if not isinstance(operations, list):
        raise FixtureError("offline fixture needs an operations list", kind="fixture")
    if not isinstance(requirements, list):
        requirements = []

    enriched: dict[str, dict[str, str]] = {}
    methods: set[str] = set()
    for operation in operations:
        if not isinstance(operation, dict):
            continue
        operation_id = operation.get("operationId")
        if not isinstance(operation_id, str) or not operation_id:
            continue
        method = str(operation.get("method", "")).upper()
        path = str(operation.get("path", ""))
        statuses = ", ".join(str(code) for code in operation.get("statuses", []))
        methods.add(method)
        enriched[operation_id] = {
            "summary": f"{method} {path}".strip(),
            "description": (
                f"{method} {path} generated from the brief. "
                f"Declared responses: {statuses or 'none'}."
            ),
        }

    requirements_total = len(requirements)
    operations_total = len(enriched)
    ambiguities = [
        "Error payload extensions beyond the RFC 9457 required fields are not defined in the brief.",
        (
            f"The brief declares {requirements_total} requirements across "
            f"{operations_total} operations; coverage is computed per method, path and status."
        ),
    ]
    if "GET" in methods:
        ambiguities.append(
            "Pagination defaults are implementation-defined; the brief does not set a page-size cap."
        )
    if methods & {"POST", "PATCH", "PUT"}:
        ambiguities.append(
            "Business validation beyond the declared field schema is not described in the brief."
        )
    return {"operations": enriched, "ambiguities": ambiguities}
