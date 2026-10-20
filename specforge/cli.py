"""SpecForge command line: `forge` generates, `verify` audits."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .brief import load_brief
from .contract_tests import write_contract_tests
from .enrich import enrich_spec
from .errors import BriefError, NebiusError, SpecForgeError
from .generator import generate_spec
from .nebius import NebiusClient
from .validator import ValidationReport, validate_spec


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dump_spec(spec: dict[str, Any], path: Path) -> None:
    path.write_text(
        yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SpecForgeError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise SpecForgeError(f"invalid YAML in {path}: {exc}") from exc


def _print_report(report: ValidationReport) -> None:
    for finding in report.findings:
        print(f"{finding.severity.upper():7s} {finding.code:20s} {finding.location}: {finding.message}")
    coverage = report.coverage
    if coverage:
        ratio = coverage.get("ratio", 0.0) * 100
        print(f"coverage: {coverage.get('covered')}/{coverage.get('total')} requirements ({ratio:.1f}%)")


def _mode_label(mode: str, model: str) -> str:
    if mode == "offline":
        return f"OFFLINE — deterministic fixtures, no network call (model label: {model})"
    if mode == "live":
        return f"LIVE — Nebius Token Factory ({model})"
    if mode == "degraded":
        return f"DEGRADED — live enrichment failed, deterministic contract kept ({model})"
    return "ENRICHMENT DISABLED — deterministic brief-only contract"


def command_forge(args: argparse.Namespace) -> int:
    brief = load_brief(args.brief)
    spec = generate_spec(brief)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = "offline" if args.offline else "live" if args.live else "auto"
    enrichment: dict[str, Any]
    if args.no_enrich:
        enrichment = {"mode": "disabled", "model": None, "ambiguities": []}
    else:
        client = NebiusClient.from_env(mode=mode, timeout=args.timeout, max_retries=args.retries)
        enrichment = client.describe()
        enrichment["mode"] = client.describe()["mode"]
        try:
            enrichment.update(enrich_spec(spec, brief, client))
        except NebiusError as exc:
            enrichment["error"] = f"{exc.kind}: {exc}"
            enrichment["mode"] = "degraded" if not client.offline else "offline"
            print(f"warning: enrichment skipped ({exc.kind}: {exc})", file=sys.stderr)
    report = validate_spec(spec, brief)
    spec_path = out_dir / "openapi.yaml"
    _dump_spec(spec, spec_path)
    artifacts = {"spec": str(spec_path), "spec_sha256": _digest(spec_path)}
    tests_count = 0
    if not args.no_contract_tests:
        tests_path, tests_count = write_contract_tests(
            spec, out_dir / "contract_tests", brief.slug, spec_path.name
        )
        artifacts["contract_tests"] = str(tests_path)
        artifacts["contract_tests_count"] = tests_count
    summary = {
        "tool": "specforge",
        "version": __version__,
        "brief": {"path": str(args.brief), "sha256": _digest(Path(args.brief))},
        "enrichment": enrichment,
        "validation": {
            "ok": report.ok(),
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "findings": [finding.as_dict() for finding in report.findings],
        },
        "coverage": report.coverage,
        "stats": report.stats,
        "artifacts": artifacts,
    }
    report_path = out_dir / "forge_report.json"
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    artifacts["report"] = str(report_path)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"SpecForge {__version__}")
        print(f"brief: {args.brief}")
        print(f"mode: {_mode_label(enrichment.get('mode', 'disabled'), enrichment.get('model') or '-')}")
        if enrichment.get("error"):
            print(f"enrichment warning: {enrichment['error']}")
        stats = report.stats
        print(f"spec: {spec_path} — paths={stats.get('paths')} operations={stats.get('operations')} "
              f"schemas={stats.get('schemas')}")
        print(f"validation: {len(report.errors)} errors, {len(report.warnings)} warnings")
        _print_report(report)
        if tests_count:
            print(f"contract tests: {artifacts['contract_tests']} ({tests_count} tests)")
        ambiguities = enrichment.get("ambiguities") or []
        if ambiguities:
            print(f"ambiguities: {len(ambiguities)} (see {report_path})")
        print(f"report: {report_path}")
    if report.errors:
        print("forge: FAILED — generated contract has validation errors", file=sys.stderr)
        return 1
    return 0


def command_verify(args: argparse.Namespace) -> int:
    spec = _load_yaml(Path(args.spec))
    brief = load_brief(args.brief) if args.brief else None
    report = validate_spec(spec, brief)
    if args.json:
        payload = report.to_dict()
        payload["spec"] = args.spec
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        version = spec.get("openapi") if isinstance(spec, dict) else None
        stats = report.stats
        print(f"verify {args.spec} (openapi {version}) — paths={stats.get('paths')} "
              f"operations={stats.get('operations')} schemas={stats.get('schemas')}")
        _print_report(report)
        verdict = "OK" if report.ok(strict=args.strict) else "FAILED"
        print(f"{verdict}: {len(report.errors)} errors, {len(report.warnings)} warnings"
              + (" (strict)" if args.strict else ""))
    return 0 if report.ok(strict=args.strict) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specforge",
        description="Generate and audit OpenAPI 3.1 contracts from a product brief.",
    )
    parser.add_argument("--version", action="version", version=f"specforge {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    forge = sub.add_parser("forge", help="generate spec and contract tests from a brief")
    forge.add_argument("--brief", required=True, help="YAML brief path")
    forge.add_argument("--out", required=True, help="output directory")
    choice = forge.add_mutually_exclusive_group()
    choice.add_argument("--offline", action="store_true", help="use deterministic fixtures")
    choice.add_argument("--live", action="store_true", help="require NEBIUS_API_KEY and call the API")
    forge.add_argument("--no-enrich", action="store_true", help="skip LLM enrichment")
    forge.add_argument("--no-contract-tests", action="store_true", help="skip pytest generation")
    forge.add_argument("--timeout", type=float, default=None, help="HTTP timeout in seconds")
    forge.add_argument("--retries", type=int, default=2, help="retry budget for 429/5xx")
    forge.add_argument("--json", action="store_true", help="print machine-readable summary")
    forge.set_defaults(handler=command_forge)
    verify = sub.add_parser("verify", help="audit an OpenAPI 3.1 document")
    verify.add_argument("spec", help="OpenAPI YAML/JSON path")
    verify.add_argument("--brief", help="brief used for requirement coverage")
    verify.add_argument("--json", action="store_true", help="print machine-readable report")
    verify.add_argument("--strict", action="store_true", help="treat warnings as failures")
    verify.set_defaults(handler=command_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (BriefError, SpecForgeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
