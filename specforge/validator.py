"""Contract validator: structure, references, operations, security, coverage."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .brief import Brief
from .generator import spec_stats
from .refs import check_references
from .structure import check_document, check_schema

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
_TEMPLATE = re.compile(r"\{([^{}]*)\}")
_SEVERITIES = ("error", "warning")


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    location: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "location": self.location,
            "message": self.message,
        }


class ValidationReport:
    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.coverage: dict[str, Any] = {}
        self.stats: dict[str, int] = {}
        self.meta: dict[str, Any] = {}

    def add(self, severity: str, code: str, location: str, message: str) -> None:
        if severity not in _SEVERITIES:
            raise ValueError(f"invalid severity {severity!r}")
        self.findings.append(Finding(severity, code, location, message))

    @property
    def errors(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.severity == "warning"]

    def ok(self, strict: bool = False) -> bool:
        if self.errors:
            return False
        return not (strict and self.warnings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok(),
            "stats": self.stats,
            "coverage": self.coverage,
            "summary": {"errors": len(self.errors), "warnings": len(self.warnings)},
            "findings": [finding.as_dict() for finding in self.findings],
            **self.meta,
        }


def _template_params(path: str, location: str, add: Any) -> list[str]:
    names: list[str] = []
    for match in _TEMPLATE.finditer(path):
        name = match.group(1)
        if not name or not name.strip():
            add("error", "PARAM-TEMPLATE", location, "empty path parameter template")
            continue
        if name in names:
            add("error", "PARAM-TEMPLATE-DUP", location, f"duplicate template parameter {name!r}")
        names.append(name)
    stripped = _TEMPLATE.sub("", path)
    if "{" in stripped or "}" in stripped:
        add("error", "PARAM-TEMPLATE", location, "unbalanced braces in path template")
    return names


def _check_parameters(raw: Any, location: str, add: Any) -> list[tuple[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        add("error", "PARAM-LIST", location, "parameters must be a list")
        return []
    seen: list[tuple[str, str]] = []
    for index, param in enumerate(raw):
        where = f"{location}/{index}"
        if not isinstance(param, dict):
            add("error", "PARAM-NOT-OBJECT", where, "parameter must be an object")
            continue
        if "$ref" in param:
            continue
        name = param.get("name")
        place = param.get("in")
        if not isinstance(name, str) or not name:
            add("error", "PARAM-NAME", f"{where}/name", "parameter name is required")
            continue
        if place not in ("path", "query", "header", "cookie"):
            add("error", "PARAM-IN", f"{where}/in", f"unsupported parameter location {place!r}")
            continue
        if place == "path" and param.get("required") is not True:
            add("error", "PARAM-PATH-REQUIRED", where, "path parameters must set required: true")
        if "schema" not in param and "content" not in param:
            add("error", "PARAM-SCHEMA", where, "parameter needs schema or content")
        if isinstance(param.get("schema"), dict):
            check_schema(param["schema"], f"{where}/schema", add)
        key = (name, place)
        if key in seen:
            add("error", "PARAM-DUPLICATE", where, f"duplicate parameter {name!r} in {place}")
        seen.append(key)
    return seen


def _check_response(response: Any, where: str, add: Any) -> None:
    if not isinstance(response, dict):
        add("error", "RESP-NOT-OBJECT", where, "response must be an object")
        return
    if "$ref" in response:
        return
    if not isinstance(response.get("description"), str) or not response["description"].strip():
        add("error", "RESP-NO-DESCRIPTION", where, "response requires a non-empty description")
    content = response.get("content")
    if content is not None:
        if not isinstance(content, dict) or not content:
            add("error", "RESP-CONTENT", f"{where}/content", "content must be a non-empty object")
        else:
            for media, entry in content.items():
                if not isinstance(media, str) or "/" not in media:
                    add("error", "RESP-MEDIA", f"{where}/content/{media}", "invalid media type")
                if not isinstance(entry, dict) or not isinstance(entry.get("schema"), dict):
                    add("error", "RESP-CONTENT-SCHEMA", f"{where}/content/{media}",
                        "media type entry requires a schema")
                elif isinstance(entry.get("schema"), dict):
                    check_schema(entry["schema"], f"{where}/content/{media}/schema", add)


def _check_operations(spec: dict[str, Any], add: Any) -> list[dict[str, Any]]:
    index: list[dict[str, Any]] = []
    operation_ids: dict[str, str] = {}
    paths = spec.get("paths") if isinstance(spec.get("paths"), dict) else {}
    for path, item in paths.items():
        if not isinstance(path, str):
            continue
        location = f"#/paths/{path}"
        if not isinstance(item, dict):
            add("error", "OP-PATH-ITEM", location, "path item must be an object")
            continue
        for key in item:
            if key in ("parameters", "servers", "summary", "description", "$ref") or key.startswith("x-"):
                continue
            if key not in HTTP_METHODS:
                add("error", "OP-UNKNOWN-KEY", f"{location}/{key}", f"unknown path item key {key!r}")
        path_params = _check_parameters(item.get("parameters"), f"{location}/parameters", add)
        template = _template_params(path, location, add)
        for method, op in item.items():
            if method not in HTTP_METHODS or not isinstance(op, dict):
                continue
            where = f"{location}/{method}"
            operation_id = op.get("operationId")
            if not isinstance(operation_id, str) or not operation_id.strip():
                add("warning", "OP-NO-OPERATIONID", where, "operationId is missing")
            elif operation_id in operation_ids:
                add("error", "OP-DUPLICATE-ID", where,
                    f"operationId {operation_id!r} already used at {operation_ids[operation_id]}")
            else:
                operation_ids[operation_id] = where
            responses = op.get("responses")
            if not isinstance(responses, dict) or not responses:
                add("error", "OP-NO-RESPONSES", where, "responses must be a non-empty object")
                responses = {}
            for code, response in responses.items():
                if code != "default" and not re.match(r"^[1-5](\d\d|XX)$", str(code)):
                    add("error", "RESP-CODE", f"{where}/responses/{code}", f"invalid status code {code!r}")
                _check_response(response, f"{where}/responses/{code}", add)
            if responses and not any(str(code).startswith("2") for code in responses):
                add("warning", "OP-NO-SUCCESS", where, "no 2xx response declared")
            op_params = _check_parameters(op.get("parameters"), f"{where}/parameters", add)
            merged = path_params + op_params
            seen: set[tuple[str, str]] = set()
            for name, place in merged:
                if (name, place) in seen and place == "path":
                    add("error", "PARAM-DUPLICATE", where, f"path parameter {name!r} declared twice")
                seen.add((name, place))
            declared_path = {name for name, place in merged if place == "path"}
            for name in template:
                if name not in declared_path:
                    add("error", "PARAM-UNDECLARED", where,
                        f"template parameter {name!r} has no path parameter declaration")
            for name in declared_path:
                if name not in template:
                    add("error", "PARAM-UNUSED", where,
                        f"path parameter {name!r} is not present in the path template")
            body = op.get("requestBody")
            if body is not None:
                if not isinstance(body, dict):
                    add("error", "OP-BODY", f"{where}/requestBody", "requestBody must be an object")
                else:
                    if method in ("get", "head", "delete"):
                        add("warning", "OP-BODY-ON-GET", f"{where}/requestBody",
                            f"request body on {method.upper()} is discouraged")
                    content = body.get("content")
                    if not isinstance(content, dict) or not content:
                        add("error", "OP-BODY-CONTENT", f"{where}/requestBody/content",
                            "request body requires content")
            index.append({
                "path": path,
                "method": method,
                "op": op,
                "location": where,
                "responses": responses,
            })
    return index


def _check_schemes(spec: dict[str, Any], add: Any) -> dict[str, Any]:
    components = spec.get("components")
    if components is not None and not isinstance(components, dict):
        return {}
    schemes = (components or {}).get("securitySchemes", {})
    if schemes is None:
        return {}
    if not isinstance(schemes, dict):
        add("error", "SEC-SCHEMES", "#/components/securitySchemes",
            "securitySchemes must be an object")
        return {}
    for name, scheme in schemes.items():
        where = f"#/components/securitySchemes/{name}"
        if not isinstance(scheme, dict):
            add("error", "SEC-SCHEME", where, "security scheme must be an object")
            continue
        stype = scheme.get("type")
        if stype not in ("apiKey", "http", "oauth2", "openIdConnect", "mutualTLS"):
            add("error", "SEC-SCHEME-TYPE", f"{where}/type", f"unsupported scheme type {stype!r}")
            continue
        if stype == "http":
            http_scheme = scheme.get("scheme")
            if not isinstance(http_scheme, str) or not http_scheme:
                add("error", "SEC-SCHEME-HTTP", f"{where}/scheme", "http scheme requires scheme")
            elif http_scheme.lower() != "bearer":
                add("warning", "SEC-SCHEME-HTTP", f"{where}/scheme",
                    f"http scheme {http_scheme!r} is unusual for this contract")
        if stype == "apiKey":
            if not isinstance(scheme.get("name"), str) or not scheme.get("name"):
                add("error", "SEC-SCHEME-APIKEY", f"{where}/name", "apiKey requires name")
            if scheme.get("in") not in ("header", "query", "cookie"):
                add("error", "SEC-SCHEME-APIKEY", f"{where}/in", "apiKey requires in")
        if stype == "oauth2" and not isinstance(scheme.get("flows"), dict):
            add("error", "SEC-SCHEME-OAUTH", f"{where}/flows", "oauth2 requires flows")
    return schemes


def _requirements(
    raw: Any, schemes: dict[str, Any], where: str, add: Any
) -> tuple[bool, set[str]]:
    if raw is None:
        return False, set()
    if not isinstance(raw, list):
        add("error", "SEC-FORM", where, "security must be a list of requirement objects")
        return False, set()
    secured = False
    names: set[str] = set()
    for index, requirement in enumerate(raw):
        at = f"{where}/{index}"
        if not isinstance(requirement, dict):
            add("error", "SEC-FORM", at, "security requirement must be an object")
            continue
        if not requirement:
            add("warning", "SEC-EMPTY-REQUIREMENT", at,
                "empty requirement object makes authentication optional")
            continue
        for name in requirement:
            names.add(name)
            if name not in schemes:
                add("error", "SEC-SCHEME-MISSING", at,
                    f"security scheme {name!r} is not defined in components.securitySchemes")
            else:
                secured = True
    return secured, names


def _check_security(spec: dict[str, Any], index: list[dict[str, Any]], add: Any) -> None:
    schemes = _check_schemes(spec, add)
    global_security = spec.get("security")
    global_secured, used = _requirements(global_security, schemes, "#/security", add)
    for entry in index:
        op = entry["op"]
        where = entry["location"]
        explicit = "security" in op
        raw = op["security"] if explicit else global_security
        secured, names = _requirements(raw, schemes, f"{where}/security", add)
        used |= names
        codes = {str(code) for code in entry["responses"]}
        if secured and "401" not in codes:
            add("error", "SEC-NO-401", where,
                "operation is secured but declares no 401 response")
        if "401" in codes and not secured:
            if explicit and raw == [] and global_secured:
                add("warning", "SEC-PUBLIC-401", where,
                    "operation is explicitly public but declares 401")
            else:
                add("warning", "SEC-ORPHAN-401", where,
                    "401 is declared but the operation is not secured")
    for name in schemes:
        if name not in used:
            add("warning", "SEC-UNUSED-SCHEME", f"#/components/securitySchemes/{name}",
                f"scheme {name!r} is never referenced")


def _check_coverage(
    brief: Brief, index: list[dict[str, Any]], report: ValidationReport
) -> None:
    def add(severity: str, code: str, location: str, message: str) -> None:
        report.add(severity, code, location, message)

    by_key = {(entry["method"].lower(), entry["path"]): entry for entry in index}
    covered: list[str] = []
    uncovered: list[str] = []
    for requirement in brief.requirements:
        entry = by_key.get((requirement.method, requirement.path))
        if entry is None:
            add("error", "COV-UNMAPPED", f"#/paths{requirement.path}",
                f"{requirement.id}: no operation {requirement.method.upper()} "
                f"{requirement.path} for requirement {requirement.text!r}")
            uncovered.append(requirement.id)
            continue
        if requirement.status is not None:
            codes = {str(code) for code in entry["responses"]}
            if str(requirement.status) not in codes:
                add("error", "COV-STATUS", f"{entry['location']}/responses",
                    f"{requirement.id}: operation does not declare status {requirement.status}")
                uncovered.append(requirement.id)
                continue
        covered.append(requirement.id)
    known = {requirement.id for requirement in brief.requirements}
    for entry in index:
        declared = entry["op"].get("x-specforge-requirements")
        if isinstance(declared, list):
            for req_id in declared:
                if req_id not in known:
                    add("warning", "COV-UNKNOWN-ID", entry["location"],
                        f"unknown requirement id {req_id!r} in x-specforge-requirements")
    total = len(brief.requirements)
    report.coverage = {
        "total": total,
        "covered": len(covered),
        "ratio": round(len(covered) / total, 4) if total else 0.0,
        "uncovered": uncovered,
        "covered_ids": covered,
    }


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[Finding] = []
    for finding in findings:
        key = (finding.severity, finding.code, finding.location, finding.message)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


def validate_spec(spec: Any, brief: Brief | None = None) -> ValidationReport:
    report = ValidationReport()

    def add(severity: str, code: str, location: str, message: str) -> None:
        report.add(severity, code, location, message)

    check_document(spec, add)
    if isinstance(spec, dict):
        check_references(spec, add)
        index = _check_operations(spec, add)
        _check_security(spec, index, add)
        if brief is not None:
            _check_coverage(brief, index, report)
        report.stats = spec_stats(spec)
    else:
        report.stats = {"paths": 0, "operations": 0, "schemas": 0}
    report.meta = {"brief": brief.source if brief is not None else None}
    report.findings = _dedupe(report.findings)
    return report

