"""Local JSON Reference resolution for OpenAPI documents."""

from __future__ import annotations

from typing import Any, Iterator
from urllib.parse import unquote

MISSING = object()


def iter_refs(node: Any, location: str = "#") -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{location}/{key}"
            if key == "$ref" and isinstance(value, str):
                yield value, child
            else:
                yield from iter_refs(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from iter_refs(value, f"{location}/{index}")


def resolve_pointer(document: Any, ref: str) -> Any:
    if ref == "#":
        return document
    if not ref.startswith("#/"):
        return MISSING
    current = document
    for raw in ref[2:].split("/"):
        token = unquote(raw).replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                return MISSING
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                return MISSING
            current = current[int(token)]
        else:
            return MISSING
    return current


def check_references(spec: Any, add: Any) -> None:
    for ref, location in iter_refs(spec):
        if ref.startswith(("http://", "https://")):
            add("error", "REF-EXTERNAL", location, f"external $ref is not allowed: {ref}")
            continue
        if not ref.startswith("#"):
            add("error", "REF-INVALID", location, f"unsupported $ref form: {ref!r}")
            continue
        if resolve_pointer(spec, ref) is MISSING:
            add("error", "REF-NOT-FOUND", location, f"$ref target does not exist: {ref}")
