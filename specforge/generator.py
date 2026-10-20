"""Deterministic brief -> OpenAPI 3.1 generator."""

from __future__ import annotations

from typing import Any

from .brief import Brief, Resource
from .schemas import build_components, field_schema

JSON = "application/json"
PROBLEM = "application/problem+json"

_METHODS = ("get", "post", "patch", "put", "delete")


def _error(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {PROBLEM: {"schema": {"$ref": "#/components/schemas/Error"}}},
    }


def _ref_response(description: str, schema: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {JSON: {"schema": {"$ref": f"#/components/schemas/{schema}"}}},
    }


def _requirements_for(brief: Brief, method: str, path: str) -> list[str]:
    return [
        req.id
        for req in brief.requirements
        if req.method == method.lower() and req.path == path
    ]


def _path_parameter(resource: Resource) -> dict[str, Any]:
    field = resource.fields[resource.id_field]
    schema = field_schema(field)
    schema.pop("readOnly", None)
    return {
        "name": resource.id_field,
        "in": "path",
        "required": True,
        "description": f"Identifier of the {resource.name}.",
        "schema": schema,
    }


def _query_parameter(field_name: str, resource: Resource) -> dict[str, Any]:
    field = resource.fields[field_name]
    schema = field_schema(field)
    schema.pop("readOnly", None)
    param: dict[str, Any] = {
        "name": field_name,
        "in": "query",
        "required": False,
        "schema": schema,
    }
    if field.type == "array":
        param["style"] = "form"
        param["explode"] = False
    return param


def _list_parameters(resource: Resource) -> list[dict[str, Any]]:
    params: list[dict[str, Any]] = [
        {
            "name": "limit",
            "in": "query",
            "required": False,
            "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        },
        {
            "name": "offset",
            "in": "query",
            "required": False,
            "schema": {"type": "integer", "minimum": 0, "default": 0},
        },
    ]
    params.extend(_query_parameter(name, resource) for name in resource.search)
    return params


def _responses(brief: Brief, resource: Resource, operation: str) -> dict[str, Any]:
    name = resource.name
    responses: dict[str, Any] = {}
    if operation == "list":
        responses["200"] = _ref_response(f"Page of {name} resources.", f"{name}List")
        responses["400"] = _error("Invalid pagination or filter parameters.")
    elif operation == "create":
        responses["201"] = _ref_response(f"Created {name}.", name)
        responses["400"] = _error("Malformed request body.")
        if 409 in resource.extra_errors:
            responses["409"] = _error(f"{name} already exists.")
    elif operation == "get":
        responses["200"] = _ref_response(f"Single {name}.", name)
    elif operation == "update":
        responses["200"] = _ref_response(f"Updated {name}.", name)
        responses["400"] = _error("Malformed request body.")
    else:
        responses["204"] = {"description": f"{name} deleted; no content."}
    if operation in ("get", "update", "delete"):
        responses["404"] = _error(f"{name} not found.")
    if brief.secured:
        responses["401"] = _error("Missing or invalid credentials.")
    if operation in ("create", "update"):
        responses["422"] = _error("Request body failed semantic validation.")
    if operation == "delete":
        for code in resource.extra_errors:
            if code != 422:
                responses[str(code)] = _error("Request conflicts with current state.")
    responses["500"] = _error("Unexpected server error.")
    return dict(sorted(responses.items(), key=lambda item: item[0]))


def _operation_id(operation: str, resource: Resource) -> str:
    if operation == "list":
        return f"list{resource.name}s"
    return f"{operation}{resource.name}"


def _operation(
    brief: Brief, resource: Resource, operation: str
) -> tuple[str, dict[str, Any]]:
    name = resource.name
    path = resource.path if operation in ("list", "create") else resource.item_path
    method = {
        "list": "get",
        "create": "post",
        "get": "get",
        "update": "patch",
        "delete": "delete",
    }[operation]
    operation_id = _operation_id(operation, resource)
    summary = {
        "list": f"List {name} resources",
        "create": f"Create {name}",
        "get": f"Get {name}",
        "update": f"Update {name}",
        "delete": f"Delete {name}",
    }[operation]
    req_ids = _requirements_for(brief, method, path)
    detail = summary + "."
    if req_ids:
        detail += " Covers: " + ", ".join(req_ids) + "."
    op: dict[str, Any] = {
        "operationId": operation_id,
        "summary": summary,
        "description": detail,
        "tags": [name],
        "responses": _responses(brief, resource, operation),
    }
    if req_ids:
        op["x-specforge-requirements"] = req_ids
    if operation in ("get", "update", "delete"):
        op["parameters"] = [_path_parameter(resource)]
    elif operation == "list":
        op["parameters"] = _list_parameters(resource)
    if operation in ("create", "update"):
        schema = f"{name}Input" if operation == "create" else f"{name}Update"
        op["requestBody"] = {
            "required": True,
            "content": {JSON: {"schema": {"$ref": f"#/components/schemas/{schema}"}}},
        }
    return method, op


def _server_url(brief: Brief) -> str:
    if brief.base_url:
        return brief.base_url
    return f"https://api.{brief.slug.replace('_', '-')}.example.invalid/v1"


def generate_spec(brief: Brief) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    tags: list[dict[str, Any]] = []
    for resource in brief.resources:
        tags.append({
            "name": resource.name,
            "description": f"{resource.name} resources declared in the brief.",
        })
        collection: dict[str, Any] = {}
        item: dict[str, Any] = {}
        for operation in resource.operations:
            method, op = _operation(brief, resource, operation)
            if operation in ("list", "create"):
                collection[method] = op
            else:
                item[method] = op
        if collection:
            paths[resource.path] = collection
        if item:
            paths[resource.item_path] = item
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": brief.name,
            "version": brief.version,
            "description": brief.description or f"Contract generated for {brief.name}.",
        },
        "servers": [{"url": _server_url(brief)}],
        "tags": tags,
        "paths": paths,
        "components": build_components(brief),
        "x-specforge": {
            "generator": "specforge",
            "slug": brief.slug,
            "brief": brief.source,
        },
    }
    if brief.secured:
        scheme = "bearerAuth" if brief.auth.type == "bearer" else "apiKeyAuth"
        spec["security"] = [{scheme: []}]
    return spec


def spec_stats(spec: dict[str, Any]) -> dict[str, int]:
    paths = spec.get("paths", {})
    operations = 0
    for item in paths.values():
        if isinstance(item, dict):
            operations += sum(1 for key in item if key.lower() in _METHODS)
    schemas = spec.get("components", {}).get("schemas", {})
    return {
        "paths": len(paths),
        "operations": operations,
        "schemas": len(schemas) if isinstance(schemas, dict) else 0,
    }
