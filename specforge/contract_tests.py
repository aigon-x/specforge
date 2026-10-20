"""Generate runnable pytest contract tests from an OpenAPI 3.1 document."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .refs import MISSING, resolve_pointer

_UUID = "00000000-0000-4000-8000-000000000000"
_TYPES = ("string", "integer", "number", "boolean", "array", "object")


def _resolve(schema: Any, spec: dict[str, Any]) -> dict[str, Any]:
    seen = 0
    while isinstance(schema, dict) and "$ref" in schema and seen < 20:
        target = resolve_pointer(spec, schema["$ref"])
        if target is MISSING or not isinstance(target, dict):
            return {}
        schema = target
        seen += 1
    return schema if isinstance(schema, dict) else {}


def _sample(schema: Any, spec: dict[str, Any], depth: int = 0) -> Any:
    resolved = _resolve(schema, spec)
    enum = resolved.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    stype = resolved.get("type")
    if isinstance(stype, list):
        stype = next((item for item in stype if item != "null"), None)
    if stype == "array":
        return []
    if stype == "object":
        return {}
    if stype == "integer":
        return 0
    if stype == "number":
        return 0.0
    if stype == "boolean":
        return True
    if stype == "string" or stype is None:
        fmt = resolved.get("format")
        if fmt == "uuid":
            return _UUID
        if fmt == "date-time":
            return "2026-01-01T00:00:00Z"
        if fmt == "date":
            return "2026-01-01"
        if fmt in ("uri", "uri-reference"):
            return "https://example.invalid/resource"
        if fmt == "email":
            return "user@example.invalid"
        return "sample"
    return None


def _body_sample(schema: Any, spec: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve(schema, spec)
    properties = resolved.get("properties")
    if not isinstance(properties, dict):
        return {}
    required = [name for name in resolved.get("required", []) if name in properties]
    names = required or list(properties)[:1]
    return {name: _sample(properties[name], spec) for name in names}


def _param_sample(param: dict[str, Any], spec: dict[str, Any]) -> Any:
    resolved = param
    if "$ref" in param:
        resolved = _resolve(param, spec)
    schema = resolved.get("schema") or {}
    value = _sample(schema, spec)
    if value is None:
        return "sample"
    return value


def _concrete_path(path: str, parameters: list[dict[str, Any]], spec: dict[str, Any]) -> str:
    result = path
    for name in _template_names(path):
        param = next(
            (item for item in parameters
             if item.get("name") == name and item.get("in") == "path"),
            None,
        )
        value = _param_sample(param, spec) if param else "sample"
        result = result.replace("{" + name + "}", str(value))
    return result


def _template_names(path: str) -> list[str]:
    names: list[str] = []
    depth = 0
    current = ""
    for char in path:
        if char == "{":
            depth += 1
            current = ""
        elif char == "}" and depth:
            depth -= 1
            names.append(current)
        elif depth:
            current += char
    return names


def _parameters(op: dict[str, Any], item: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for raw in list(item.get("parameters") or []) + list(op.get("parameters") or []):
        if not isinstance(raw, dict):
            continue
        merged.append(_resolve(raw, spec) if "$ref" in raw else raw)
    return merged


def _auth_header(spec: dict[str, Any]) -> tuple[str, str]:
    schemes = spec.get("components", {}).get("securitySchemes", {})
    if isinstance(schemes, dict):
        for scheme in schemes.values():
            if not isinstance(scheme, dict):
                continue
            if scheme.get("type") == "http" and str(scheme.get("scheme", "")).lower() == "bearer":
                return "Authorization", "Bearer "
            if scheme.get("type") == "apiKey" and isinstance(scheme.get("name"), str):
                return scheme["name"], ""
    return "Authorization", "Bearer "


def _query_string(parameters: list[dict[str, Any]], spec: dict[str, Any]) -> str:
    parts: list[str] = []
    for param in parameters:
        if param.get("in") != "query" or param.get("required") is not True:
            continue
        value = _param_sample(param, spec)
        if isinstance(value, list):
            value = ",".join(str(item) for item in value)
        parts.append(f"{param['name']}={value}")
    return ("?" + "&".join(parts)) if parts else ""


def build_test_plan(spec: dict[str, Any]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    paths = spec.get("paths", {})
    for path in sorted(paths):
        item = paths[path]
        if not isinstance(item, dict):
            continue
        for method in sorted(item):
            op = item[method]
            if not isinstance(op, dict) or "operationId" not in op:
                continue
            params = _parameters(op, item, spec)
            concrete = _concrete_path(path, params, spec)
            target = concrete + _query_string(params, spec)
            responses = op.get("responses", {})
            success = sorted(
                (code for code in responses if str(code).startswith("2")),
                key=lambda code: (str(code) != "200", str(code)),
            )
            op_id = op["operationId"]
            body = None
            if isinstance(op.get("requestBody"), dict):
                content = op["requestBody"].get("content", {})
                if isinstance(content, dict) and content:
                    media = content.get("application/json") or next(iter(content.values()))
                    if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                        body = _body_sample(media["schema"], spec)
            if success:
                code = int(success[0]) if str(success[0]).isdigit() else 200
                required: list[str] = []
                types: dict[str, str] = {}
                response = responses[success[0]]
                if isinstance(response, dict):
                    content = response.get("content", {})
                    media = content.get("application/json") if isinstance(content, dict) else None
                    if isinstance(media, dict):
                        schema = _resolve(media.get("schema", {}), spec)
                        props = schema.get("properties", {})
                        if isinstance(props, dict):
                            required = [name for name in schema.get("required", []) if name in props]
                            for name, child in props.items():
                                ctype = _resolve(child, spec).get("type")
                                if isinstance(ctype, str) and ctype in _TYPES:
                                    types[name] = ctype
                plan.append({
                    "name": f"test_{op_id}_happy",
                    "method": method.upper(),
                    "path": target,
                    "expect": code,
                    "body": body,
                    "auth": True,
                    "required": required,
                    "types": types,
                })
            for code in ("401", "404", "422"):
                if str(code) not in {str(key) for key in responses}:
                    continue
                if code == "422" and body is None:
                    continue
                plan.append({
                    "name": f"test_{op_id}_{code}",
                    "method": method.upper(),
                    "path": target,
                    "expect": int(code),
                    "body": ({} if code == "422" else body),
                    "auth": code != "401",
                    "required": [],
                    "types": {},
                })
    return plan


_HEADER = '''"""Generated by SpecForge. Do not edit by hand.

Run against a live service:
    SPECFORGE_BASE_URL=https://api.example.com SPECFORGE_TOKEN=... pytest -q
Without SPECFORGE_BASE_URL every test is skipped.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

BASE_URL = os.environ.get("SPECFORGE_BASE_URL", "").rstrip("/")
TOKEN = os.environ.get("SPECFORGE_TOKEN", "")
TIMEOUT = float(os.environ.get("SPECFORGE_TIMEOUT", "10"))
AUTH_HEADER = {header!r}
AUTH_PREFIX = {prefix!r}

pytestmark = pytest.mark.skipif(not BASE_URL, reason="SPECFORGE_BASE_URL is not set")


def _request(method, path, body=None, auth=True):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {{"Accept": "application/json"}}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if auth and TOKEN:
        headers[AUTH_HEADER] = AUTH_PREFIX + TOKEN
    request = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()


def _check_json(raw, required, types):
    if not raw:
        return
    payload = json.loads(raw.decode("utf-8"))
    assert isinstance(payload, dict), "response body must be a JSON object"
    for name in required:
        assert name in payload, f"missing required field {{name!r}}"
    for name, expected in types.items():
        if name not in payload or payload[name] is None:
            continue
        value = payload[name]
        if expected == "array":
            assert isinstance(value, list), f"{{name}} must be an array"
        elif expected == "object":
            assert isinstance(value, dict), f"{{name}} must be an object"
        elif expected == "integer":
            assert isinstance(value, int) and not isinstance(value, bool), f"{{name}} must be an integer"
        elif expected == "number":
            assert isinstance(value, (int, float)) and not isinstance(value, bool), f"{{name}} must be a number"
        elif expected == "boolean":
            assert isinstance(value, bool), f"{{name}} must be a boolean"
        elif expected == "string":
            assert isinstance(value, str), f"{{name}} must be a string"
'''


def generate_contract_tests(spec: dict[str, Any], spec_name: str = "openapi.yaml") -> str:
    header, prefix = _auth_header(spec)
    parts = [_HEADER.format(header=header, prefix=prefix)]
    parts.append(f"\n# source: {spec_name}\n")
    for test in build_test_plan(spec):
        body = "None" if test["body"] is None else repr(test["body"])
        parts.append(
            f"\n\ndef {test['name']}():\n"
            f"    status, content_type, raw = _request({test['method']!r}, {test['path']!r},"
            f" body={body}, auth={test['auth']!r})\n"
            f"    assert status == {test['expect']}, f\"expected {test['expect']}, got {{status}}\"\n"
        )
        if test["expect"] < 300:
            parts.append(
                "    _check_json(raw, "
                f"{test['required']!r}, {test['types']!r})\n"
            )
    return "".join(parts) + "\n"


def write_contract_tests(
    spec: dict[str, Any], out_dir: str | Path, slug: str = "api", spec_name: str = "openapi.yaml"
) -> tuple[Path, int]:
    source = generate_contract_tests(spec, spec_name)
    compile(source, f"<generated:{slug}>", "exec")
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"test_contract_{slug}.py"
    path.write_text(source, encoding="utf-8")
    return path, len(build_test_plan(spec))
