"""Optional LLM enrichment. Prose only: never endpoints, schemas or status codes."""

from __future__ import annotations

import json
from typing import Any

from .brief import Brief
from .errors import NebiusError
from .nebius import NebiusClient

SYSTEM_PROMPT = (
    "You are an API contract assistant. Reply with one JSON object and no markdown. "
    'Shape: {"operations": {"<operationId>": {"summary": "...", "description": "..."}}, '
    '"ambiguities": ["..."]}. Never invent endpoints, parameters, fields or status codes. '
    "Keep every description under 300 characters."
)


def build_messages(brief: Brief, spec: dict[str, Any]) -> list[dict[str, str]]:
    operations: list[dict[str, Any]] = []
    paths = spec.get("paths", {})
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if not isinstance(op, dict) or "operationId" not in op:
                continue
            operations.append({
                "operationId": op["operationId"],
                "method": method.upper(),
                "path": path,
                "summary": op.get("summary", ""),
                "statuses": sorted(str(code) for code in op.get("responses", {})),
            })
    requirements = [
        {"id": req.id, "text": req.text, "method": req.method.upper(), "path": req.path}
        for req in brief.requirements
    ]
    user = {
        "task": "Improve operation summaries and descriptions; list ambiguities.",
        "api": {"name": brief.name, "version": brief.version, "description": brief.description},
        "operations": operations,
        "requirements": requirements,
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False, sort_keys=True)},
    ]


def parse_payload(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise NebiusError("no JSON object in fenced completion", kind="invalid_json")
        text = text[start:end + 1]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NebiusError(f"completion is not JSON: {exc}", kind="invalid_json") from exc
    if not isinstance(payload, dict):
        raise NebiusError("completion must be a JSON object", kind="invalid_json")
    operations = payload.get("operations", {})
    if operations is not None and not isinstance(operations, dict):
        raise NebiusError("operations must be an object", kind="invalid_json")
    ambiguities = payload.get("ambiguities", [])
    if ambiguities is not None and not isinstance(ambiguities, list):
        raise NebiusError("ambiguities must be a list", kind="invalid_json")
    return payload


def apply_enrichment(
    spec: dict[str, Any],
    payload: dict[str, Any],
    *,
    model: str,
    mode: str,
) -> dict[str, Any]:
    operations = payload.get("operations") or {}
    index: dict[str, dict[str, Any]] = {}
    for item in spec.get("paths", {}).values():
        if not isinstance(item, dict):
            continue
        for value in item.values():
            if isinstance(value, dict) and isinstance(value.get("operationId"), str):
                index[value["operationId"]] = value
    applied: list[str] = []
    for operation_id, update in operations.items():
        operation = index.get(operation_id)
        if operation is None or not isinstance(update, dict):
            continue
        changed = False
        for key in ("summary", "description"):
            value = update.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                if key == "description" and operation.get("x-specforge-requirements"):
                    ids = ", ".join(operation["x-specforge-requirements"])
                    text = f"{text} Covers: {ids}."
                operation[key] = text[:400]
                changed = True
        if changed:
            operation["x-specforge-enriched"] = True
            applied.append(operation_id)
    ambiguities = [
        item.strip() for item in payload.get("ambiguities", [])
        if isinstance(item, str) and item.strip()
    ]
    meta = {
        "model": model,
        "mode": mode,
        "applied_operations": applied,
        "ignored_operations": sorted(set(operations) - set(applied)),
        "ambiguities": ambiguities,
    }
    spec.setdefault("x-specforge-enrichment", {}).update({
        "provider": "nebius-token-factory",
        "model": model,
        "mode": mode,
        "applied_operations": applied,
        "ambiguities": ambiguities,
    })
    return meta


def enrich_spec(
    spec: dict[str, Any], brief: Brief, client: NebiusClient
) -> dict[str, Any]:
    completion = client.complete(build_messages(brief, spec), task="enrich")
    payload = parse_payload(completion.content)
    meta = apply_enrichment(
        spec, payload, model=completion.model, mode=completion.mode
    )
    meta.update({
        "mode": completion.mode,
        "model": completion.model,
        "attempts": completion.attempts,
        "latency_ms": completion.latency_ms,
        "offline": completion.offline,
    })
    return meta
