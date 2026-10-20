"""Brief model and YAML loader. Only the parts the generator needs are modelled."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import BriefError

try:  # PyYAML is present in the runtime image; fail loudly if it is not.
    import yaml
except ImportError:  # pragma: no cover - environment guard
    yaml = None

METHODS = ("get", "post", "patch", "put", "delete")
OPERATIONS = ("list", "create", "get", "update", "delete")
FIELD_TYPES = ("string", "integer", "number", "boolean", "array", "object")
ERROR_CODES = (400, 401, 403, 404, 409, 422, 429, 500)

_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SLUG = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    required: bool = False
    read_only: bool = False
    format: str | None = None
    description: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    enum: tuple[Any, ...] = ()
    items_type: str | None = None


@dataclass(frozen=True)
class Resource:
    name: str
    path: str
    id_field: str
    operations: tuple[str, ...]
    fields: dict[str, FieldSpec]
    search: tuple[str, ...] = ()
    extra_errors: tuple[int, ...] = ()

    @property
    def item_path(self) -> str:
        return f"{self.path}/{{{self.id_field}}}"


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    method: str
    path: str
    status: int | None = None


@dataclass(frozen=True)
class Auth:
    type: str = "none"
    header: str = "Authorization"
    scheme: str = "bearer"


@dataclass(frozen=True)
class Brief:
    name: str
    slug: str
    version: str
    description: str
    base_url: str | None
    auth: Auth
    resources: tuple[Resource, ...]
    requirements: tuple[Requirement, ...]
    source: str = "<memory>"

    @property
    def secured(self) -> bool:
        return self.auth.type != "none"

    def operation_ids(self) -> list[str]:
        return [f"{op}{res.name}" for res in self.resources for op in res.operations]


def _mapping(value: Any, where: str, problems: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        problems.append(f"{where}: expected a mapping")
        return {}
    return value


def _string(value: Any, where: str, problems: list[str], *, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{where}: expected a non-empty string")
        return ""
    return value.strip()


def _number(value: Any, where: str, problems: list[str]) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        problems.append(f"{where}: expected a number")
        return None
    return float(value)


def _integer(value: Any, where: str, problems: list[str]) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        problems.append(f"{where}: expected an integer")
        return None
    return value


def _parse_field(name: str, raw: Any, where: str, problems: list[str]) -> FieldSpec | None:
    if isinstance(raw, str):
        raw = {"type": raw}
    data = _mapping(raw, where, problems)
    ftype = data.get("type", "string")
    if not isinstance(ftype, str) or ftype not in FIELD_TYPES:
        problems.append(f"{where}.type: unsupported type {ftype!r}")
        return None
    formats = data.get("format")
    if formats is not None and not isinstance(formats, str):
        problems.append(f"{where}.format: expected a string")
        formats = None
    enum = data.get("enum", ())
    if not isinstance(enum, (list, tuple)) or (enum and len(set(enum)) != len(enum)):
        problems.append(f"{where}.enum: expected a list of unique values")
        enum = ()
    items_type = data.get("items")
    if isinstance(items_type, dict):
        items_type = items_type.get("type")
    if ftype == "array":
        if items_type not in FIELD_TYPES or items_type in ("array", "object"):
            problems.append(f"{where}.items.type: array needs a scalar item type")
            return None
    elif items_type is not None:
        problems.append(f"{where}.items: only valid for arrays")
        items_type = None
    for key in sorted(set(data) - {
        "type", "format", "required", "read_only", "minimum", "maximum",
        "min_length", "max_length", "enum", "items", "description", "example",
    }):
        problems.append(f"{where}: unknown field key {key!r}")
    min_len = _integer(data.get("min_length"), f"{where}.min_length", problems)
    max_len = _integer(data.get("max_length"), f"{where}.max_length", problems)
    if min_len is not None and max_len is not None and min_len > max_len:
        problems.append(f"{where}: min_length > max_length")
    minimum = _number(data.get("minimum"), f"{where}.minimum", problems)
    maximum = _number(data.get("maximum"), f"{where}.maximum", problems)
    if minimum is not None and maximum is not None and minimum > maximum:
        problems.append(f"{where}: minimum > maximum")
    if ftype not in ("integer", "number") and (minimum is not None or maximum is not None):
        problems.append(f"{where}: numeric bounds on non-numeric type")
    if ftype in ("integer", "number") and (min_len is not None or max_len is not None):
        problems.append(f"{where}: min_length/max_length on numeric type")
    return FieldSpec(
        name=name,
        type=ftype,
        required=bool(data.get("required", False)),
        read_only=bool(data.get("read_only", False)),
        format=formats,
        description=data.get("description") if isinstance(data.get("description"), str) else None,
        minimum=minimum,
        maximum=maximum,
        min_length=min_len,
        max_length=max_len,
        enum=tuple(enum),
        items_type=items_type if isinstance(items_type, str) else None,
    )


def _parse_resource(raw: Any, index: int, problems: list[str]) -> Resource | None:
    where = f"resources[{index}]"
    before = len(problems)
    data = _mapping(raw, where, problems)
    name = _string(data.get("name"), f"{where}.name", problems)
    if name and not _IDENT.match(name):
        problems.append(f"{where}.name: must be a plain identifier, got {name!r}")
    path = _string(data.get("path"), f"{where}.path", problems)
    if path and not path.startswith("/"):
        problems.append(f"{where}.path: must start with '/'")
    if path and ("{" in path or path.endswith("/")):
        problems.append(f"{where}.path: collection path must not contain '{{' or end with '/'")
    ops_raw = data.get("operations")
    ops: list[str] = []
    if not isinstance(ops_raw, list) or not ops_raw:
        problems.append(f"{where}.operations: expected a non-empty list")
    else:
        for op in ops_raw:
            if not isinstance(op, str) or op not in OPERATIONS:
                problems.append(f"{where}.operations: unsupported operation {op!r}")
            elif op in ops:
                problems.append(f"{where}.operations: duplicate {op!r}")
            else:
                ops.append(op)
    fields_raw = _mapping(data.get("fields"), f"{where}.fields", problems)
    fields: dict[str, FieldSpec] = {}
    for fname, fraw in fields_raw.items():
        if not isinstance(fname, str) or not _FIELD.match(fname):
            problems.append(f"{where}.fields: invalid field name {fname!r}")
            continue
        parsed = _parse_field(fname, fraw, f"{where}.fields.{fname}", problems)
        if parsed is not None:
            fields[fname] = parsed
    if not fields:
        problems.append(f"{where}.fields: at least one field is required")
    id_field = data.get("id_field", "id")
    if not isinstance(id_field, str) or id_field not in fields:
        problems.append(f"{where}.id_field: {id_field!r} is not a declared field")
        id_field = "id"
    elif id_field in fields:
        ident = fields[id_field]
        if ident.type not in ("string", "integer"):
            problems.append(f"{where}.id_field: must be a string or integer field")
        if not ident.read_only:
            problems.append(f"{where}.id_field: id field must be read_only")
    search_raw = data.get("search", ())
    if not isinstance(search_raw, (list, tuple)):
        problems.append(f"{where}.search: expected a list")
        search_raw = ()
    search: list[str] = []
    for sname in search_raw:
        if sname not in fields:
            problems.append(f"{where}.search: unknown field {sname!r}")
        elif fields[sname].type == "object":
            problems.append(f"{where}.search: object field {sname!r} cannot be filtered")
        else:
            search.append(sname)
    extra_raw = data.get("extra_errors", ())
    if not isinstance(extra_raw, (list, tuple)):
        problems.append(f"{where}.extra_errors: expected a list")
        extra_raw = ()
    extra: list[int] = []
    for code in extra_raw:
        if code not in ERROR_CODES:
            problems.append(f"{where}.extra_errors: unsupported status {code!r}")
        elif code not in extra:
            extra.append(int(code))
    for key in sorted(set(data) - {"name", "path", "id_field", "operations", "fields", "search", "extra_errors"}):
        if not key.startswith("x-"):
            problems.append(f"{where}: unknown key {key!r}")
    if len(problems) > before:
        return None
    return Resource(
        name=name,
        path=path,
        id_field=id_field,
        operations=tuple(ops),
        fields=fields,
        search=tuple(search),
        extra_errors=tuple(extra),
    )


def _parse_auth(raw: Any, problems: list[str]) -> Auth:
    if raw is None:
        return Auth()
    data = _mapping(raw, "auth", problems)
    atype = data.get("type", "none")
    if atype not in ("none", "bearer", "api_key"):
        problems.append(f"auth.type: unsupported {atype!r}")
        return Auth()
    header = data.get("header", "Authorization" if atype == "bearer" else "X-API-Key")
    if not isinstance(header, str) or not header:
        problems.append("auth.header: expected a non-empty string")
        header = "Authorization"
    scheme = data.get("scheme", "bearer")
    if atype == "bearer" and scheme != "bearer":
        problems.append("auth.scheme: only 'bearer' is supported for type bearer")
    for key in sorted(set(data) - {"type", "header", "scheme"}):
        problems.append(f"auth: unknown key {key!r}")
    return Auth(type=atype, header=header, scheme=scheme)


def _parse_requirement(raw: Any, index: int, problems: list[str]) -> Requirement | None:
    where = f"requirements[{index}]"
    before = len(problems)
    data = _mapping(raw, where, problems)
    rid = _string(data.get("id"), f"{where}.id", problems)
    text = _string(data.get("text"), f"{where}.text", problems)
    method = data.get("method")
    if not isinstance(method, str) or method.lower() not in METHODS:
        problems.append(f"{where}.method: expected one of {', '.join(METHODS)}")
        method = ""
    path = _string(data.get("path"), f"{where}.path", problems)
    if path and not path.startswith("/"):
        problems.append(f"{where}.path: must start with '/'")
    status = _integer(data.get("status"), f"{where}.status", problems)
    if status is not None and not 100 <= status <= 599:
        problems.append(f"{where}.status: expected HTTP status 100..599")
    for key in sorted(set(data) - {"id", "text", "method", "path", "status"}):
        problems.append(f"{where}: unknown key {key!r}")
    if len(problems) > before:
        return None
    return Requirement(id=rid, text=text, method=method.lower(), path=path, status=status)


def parse_brief(raw: Any, source: str = "<memory>") -> Brief:
    problems: list[str] = []
    data = _mapping(raw, source, problems)
    name = _string(data.get("name"), "name", problems)
    version = data.get("version", "1.0.0")
    version = str(version).strip() if isinstance(version, (str, int, float)) else ""
    if not version:
        problems.append("version: expected a non-empty version string")
    description = data.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str):
        problems.append("description: expected a string")
        description = ""
    slug = data.get("slug") or re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "api"
    if not isinstance(slug, str) or not _SLUG.match(slug):
        problems.append(f"slug: invalid {slug!r}")
        slug = "api"
    base_url = data.get("base_url")
    if base_url is not None and (not isinstance(base_url, str) or not base_url.startswith(("http://", "https://"))):
        problems.append("base_url: expected an http(s) URL")
        base_url = None
    auth = _parse_auth(data.get("auth"), problems)
    resources_raw = data.get("resources")
    resources: list[Resource] = []
    paths: set[str] = set()
    names: set[str] = set()
    if not isinstance(resources_raw, list) or not resources_raw:
        problems.append("resources: expected a non-empty list")
    else:
        for i, rraw in enumerate(resources_raw):
            res = _parse_resource(rraw, i, problems)
            if res is None:
                continue
            if res.path in paths:
                problems.append(f"resources[{i}].path: duplicate path {res.path!r}")
            if res.name.lower() in names:
                problems.append(f"resources[{i}].name: duplicate resource {res.name!r}")
            paths.add(res.path)
            names.add(res.name.lower())
            resources.append(res)
    reqs_raw = data.get("requirements")
    requirements: list[Requirement] = []
    if not isinstance(reqs_raw, list) or not reqs_raw:
        problems.append("requirements: at least one requirement is required")
    else:
        seen: set[str] = set()
        for i, qraw in enumerate(reqs_raw):
            req = _parse_requirement(qraw, i, problems)
            if req is None:
                continue
            if req.id in seen:
                problems.append(f"requirements[{i}].id: duplicate {req.id!r}")
                continue
            seen.add(req.id)
            requirements.append(req)
    for key in sorted(set(data) - {
        "name", "slug", "version", "description", "base_url", "auth", "resources", "requirements", "notes",
    }):
        if not key.startswith("x-"):
            problems.append(f"unknown top-level key {key!r}")
    if problems:
        raise BriefError(problems, source)
    return Brief(
        name=name,
        slug=slug,
        version=version,
        description=description.strip(),
        base_url=base_url,
        auth=auth,
        resources=tuple(resources),
        requirements=tuple(requirements),
        source=source,
    )


def load_brief(path: str | Path) -> Brief:
    file_path = Path(path)
    if yaml is None:  # pragma: no cover - environment guard
        raise BriefError(["PyYAML is not installed"], str(file_path))
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BriefError([f"cannot read brief: {exc}"], str(file_path)) from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise BriefError([f"invalid YAML: {exc}"], str(file_path)) from exc
    return parse_brief(raw, str(file_path))
