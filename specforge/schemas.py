"""JSON Schema components derived from brief resources."""

from __future__ import annotations

from typing import Any

from .brief import Brief, FieldSpec, Resource


def field_schema(field: FieldSpec) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": field.type}
    if field.format:
        schema["format"] = field.format
    if field.description:
        schema["description"] = field.description
    if field.enum:
        schema["enum"] = list(field.enum)
    if field.type == "array":
        schema["items"] = {"type": field.items_type}
    if field.type in ("integer", "number"):
        if field.minimum is not None:
            schema["minimum"] = field.minimum
        if field.maximum is not None:
            schema["maximum"] = field.maximum
    if field.type == "string":
        if field.min_length is not None:
            schema["minLength"] = field.min_length
        if field.max_length is not None:
            schema["maxLength"] = field.max_length
    if field.read_only:
        schema["readOnly"] = True
    return schema


def object_schema(
    resource: Resource,
    *,
    include_read_only: bool = True,
    require_fields: bool = True,
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, field in resource.fields.items():
        if field.read_only and not include_read_only:
            continue
        properties[name] = field_schema(field)
        if require_fields and field.required and not field.read_only:
            required.append(name)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def collection_schema(resource: Resource) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"$ref": f"#/components/schemas/{resource.name}"},
            },
            "total": {"type": "integer", "minimum": 0},
        },
        "required": ["items", "total"],
        "additionalProperties": False,
    }


def error_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "RFC 9457 problem details.",
        "properties": {
            "type": {"type": "string", "format": "uri-reference"},
            "title": {"type": "string"},
            "status": {"type": "integer", "minimum": 400, "maximum": 599},
            "detail": {"type": "string"},
            "instance": {"type": "string", "format": "uri-reference"},
        },
        "required": ["type", "title", "status"],
        "additionalProperties": False,
    }


def security_schemes(brief: Brief) -> dict[str, Any]:
    if brief.auth.type == "bearer":
        return {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "description": "Bearer token issued by the platform.",
            }
        }
    if brief.auth.type == "api_key":
        return {
            "apiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": brief.auth.header,
            }
        }
    return {}


def build_components(brief: Brief) -> dict[str, Any]:
    schemas: dict[str, Any] = {"Error": error_schema()}
    for resource in brief.resources:
        schemas[resource.name] = object_schema(resource)
        schemas[f"{resource.name}Input"] = object_schema(
            resource, include_read_only=False
        )
        schemas[f"{resource.name}Update"] = object_schema(
            resource, include_read_only=False, require_fields=False
        )
        schemas[f"{resource.name}List"] = collection_schema(resource)
    components: dict[str, Any] = {"schemas": schemas}
    schemes = security_schemes(brief)
    if schemes:
        components["securitySchemes"] = schemes
    return components
