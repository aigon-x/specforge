"""Structural checks for OpenAPI 3.1 documents and JSON Schemas."""

from __future__ import annotations

import re
from typing import Any

_VERSION = re.compile(r"^3\.1\.\d+$")
_TYPES = {"null", "boolean", "object", "array", "number", "string", "integer"}
_SCHEMA_KEYS = {
    "$ref", "$schema", "$id", "$anchor", "$defs", "title", "description", "type",
    "format", "enum", "const", "default", "examples", "example", "deprecated",
    "readOnly", "writeOnly", "properties", "required", "additionalProperties",
    "items", "prefixItems", "minItems", "maxItems", "uniqueItems", "minLength",
    "maxLength", "pattern", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "multipleOf", "allOf", "anyOf", "oneOf", "not",
    "discriminator", "contentEncoding", "contentMediaType",
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _add_schema_key_warnings(schema: dict[str, Any], location: str, add: Any) -> None:
    for key in schema:
        if key in _SCHEMA_KEYS or key.startswith("x-"):
            continue
        add("warning", "SCHEMA-UNKNOWN-KEY", f"{location}/{key}", f"unknown schema keyword {key!r}")


def check_schema(schema: Any, location: str, add: Any, seen: set[int] | None = None) -> None:
    if not isinstance(schema, dict):
        add("error", "SCHEMA-NOT-OBJECT", location, "schema must be an object")
        return
    if seen is None:
        seen = set()
    if id(schema) in seen:
        return
    seen.add(id(schema))
    _add_schema_key_warnings(schema, location, add)
    if "nullable" in schema:
        add("error", "SCHEMA-NULLABLE-3_0", f"{location}/nullable",
            "nullable is OpenAPI 3.0; use type: [..., 'null'] in 3.1")
    if "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#"):
            add("error", "SCHEMA-REF-FORM", f"{location}/$ref",
                "only local $ref values are supported")
    stype = schema.get("type")
    if isinstance(stype, str):
        if stype not in _TYPES:
            add("error", "SCHEMA-TYPE", f"{location}/type", f"unsupported type {stype!r}")
    elif isinstance(stype, list):
        if not stype or len(set(map(str, stype))) != len(stype):
            add("error", "SCHEMA-TYPE", f"{location}/type", "type list must be non-empty and unique")
        for entry in stype:
            if entry not in _TYPES:
                add("error", "SCHEMA-TYPE", f"{location}/type", f"unsupported type {entry!r}")
    elif stype is not None:
        add("error", "SCHEMA-TYPE", f"{location}/type", "type must be a string or a list of strings")
    if isinstance(schema.get("enum"), list):
        values = schema["enum"]
        if not values:
            add("error", "SCHEMA-ENUM-EMPTY", f"{location}/enum", "enum must not be empty")
        if len({repr(value) for value in values}) != len(values):
            add("error", "SCHEMA-ENUM-DUP", f"{location}/enum", "enum values must be unique")
    elif "enum" in schema:
        add("error", "SCHEMA-ENUM", f"{location}/enum", "enum must be a list")
    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            add("error", "SCHEMA-PROPERTIES", f"{location}/properties", "properties must be an object")
        else:
            for name, child in properties.items():
                check_schema(child, f"{location}/properties/{name}", add, seen)
    required = schema.get("required")
    if required is not None:
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            add("error", "SCHEMA-REQUIRED", f"{location}/required", "required must be a list of strings")
        else:
            if len(set(required)) != len(required):
                add("error", "SCHEMA-REQUIRED-DUP", f"{location}/required", "required entries must be unique")
            if isinstance(properties, dict):
                missing = [item for item in required if item not in properties]
                for item in missing:
                    add("error", "SCHEMA-REQUIRED-UNKNOWN", f"{location}/required",
                        f"required field {item!r} is not declared in properties")
    if schema.get("type") == "object" and "properties" not in schema and "additionalProperties" not in schema:
        add("warning", "SCHEMA-OBJECT-OPEN", location,
            "object schema has neither properties nor additionalProperties")
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        check_schema(additional, f"{location}/additionalProperties", add, seen)
    elif additional is not None and not isinstance(additional, bool):
        add("error", "SCHEMA-ADDITIONAL", f"{location}/additionalProperties",
            "must be a boolean or a schema")
    if schema.get("type") == "array":
        if "items" not in schema and "prefixItems" not in schema:
            add("error", "SCHEMA-ITEMS-MISSING", location, "array schema requires items")
        if isinstance(schema.get("items"), dict):
            check_schema(schema["items"], f"{location}/items", add, seen)
        if isinstance(schema.get("prefixItems"), list):
            for index, child in enumerate(schema["prefixItems"]):
                check_schema(child, f"{location}/prefixItems/{index}", add, seen)
    for key in ("allOf", "anyOf", "oneOf"):
        if key in schema:
            entries = schema[key]
            if not isinstance(entries, list) or not entries:
                add("error", "SCHEMA-COMBINATOR", f"{location}/{key}",
                    f"{key} must be a non-empty list")
            else:
                for index, child in enumerate(entries):
                    check_schema(child, f"{location}/{key}/{index}", add, seen)
    if isinstance(schema.get("not"), dict):
        check_schema(schema["not"], f"{location}/not", add, seen)
    for key in ("minLength", "maxLength", "minItems", "maxItems"):
        if key in schema:
            value = schema[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                add("error", "SCHEMA-BOUND", f"{location}/{key}", "must be a non-negative integer")
    lo, hi = schema.get("minLength"), schema.get("maxLength")
    if isinstance(lo, int) and isinstance(hi, int) and lo > hi:
        add("error", "SCHEMA-LENGTH-RANGE", location, "minLength is greater than maxLength")
    for key in ("minimum", "maximum"):
        if key in schema and not _is_number(schema[key]):
            add("error", "SCHEMA-BOUND", f"{location}/{key}", "must be a number")
    for key in ("exclusiveMinimum", "exclusiveMaximum"):
        if key in schema and not _is_number(schema[key]):
            add("error", "SCHEMA-EXCLUSIVE-BOOL", f"{location}/{key}",
                "OpenAPI 3.1 expects a number, not a boolean")


def check_document(spec: Any, add: Any) -> None:
    if not isinstance(spec, dict):
        add("error", "SPEC-ROOT", "#", "document root must be an object")
        return
    version = spec.get("openapi")
    if not isinstance(version, str) or not _VERSION.match(version):
        add("error", "SPEC-VERSION", "#/openapi", f"expected OpenAPI 3.1.x, got {version!r}")
    info = spec.get("info")
    if not isinstance(info, dict):
        add("error", "SPEC-INFO", "#/info", "info object is required")
    else:
        for key in ("title", "version"):
            if not isinstance(info.get(key), str) or not info[key].strip():
                add("error", "SPEC-INFO", f"#/info/{key}", "non-empty string required")
    servers = spec.get("servers")
    if servers is not None:
        if not isinstance(servers, list):
            add("error", "SPEC-SERVERS", "#/servers", "servers must be a list")
        else:
            for index, server in enumerate(servers):
                if not isinstance(server, dict) or not isinstance(server.get("url"), str):
                    add("error", "SPEC-SERVERS", f"#/servers/{index}", "server needs a string url")
                elif not server["url"].startswith(("http://", "https://", "/")):
                    add("error", "SPEC-SERVERS", f"#/servers/{index}/url",
                        "server url must be absolute http(s) or a relative path")
    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        add("error", "SPEC-PATHS-EMPTY", "#/paths", "paths must be a non-empty object")
        paths = {}
    normalized: dict[str, str] = {}
    for path in paths:
        if not isinstance(path, str) or not path.startswith("/"):
            add("error", "SPEC-PATH-KEY", f"#/paths/{path}", "path keys must start with '/'")
            continue
        if "?" in path or "#" in path:
            add("error", "SPEC-PATH-KEY", f"#/paths/{path}", "path keys must not contain ? or #")
        template = re.sub(r"\{[^}]*\}", "{}", path)
        if template in normalized:
            add("error", "SPEC-PATH-AMBIGUOUS", f"#/paths/{path}",
                f"same template as {normalized[template]}")
        else:
            normalized[template] = path
    components = spec.get("components")
    if components is not None and not isinstance(components, dict):
        add("error", "SPEC-COMPONENTS", "#/components", "components must be an object")
        components = {}
    schemas = (components or {}).get("schemas", {})
    if schemas is not None and not isinstance(schemas, dict):
        add("error", "SPEC-SCHEMAS", "#/components/schemas", "schemas must be an object")
    elif schemas:
        for name, schema in schemas.items():
            check_schema(schema, f"#/components/schemas/{name}", add)
