"""SpecForge web UI: run an offline forge from the browser."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from specforge import __version__
from specforge.cli import main as forge_main

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = Path(__file__).resolve().parent
BRIEFS_DIR = ROOT / "briefs"
OUT_DIR = Path(os.environ.get("SPECFORGE_WEB_OUT", str(ROOT / "out" / "web")))
_BRIEF_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SUFFIXES = (".yaml", ".yml")

app = FastAPI(title="SpecForge web", version=__version__)


class ForgeRequest(BaseModel):
    brief: str


def _brief_names() -> list[str]:
    return sorted(
        path.stem
        for path in BRIEFS_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in _SUFFIXES
    )


def _brief_path(name: str) -> Path:
    stem = name
    for suffix in _SUFFIXES:
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    if not _BRIEF_NAME.fullmatch(stem):
        raise HTTPException(status_code=404, detail=f"unknown brief: {name}")
    for suffix in _SUFFIXES:
        candidate = BRIEFS_DIR / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    raise HTTPException(status_code=404, detail=f"unknown brief: {name}")


def _payload(brief_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    stats = report.get("stats") or {}
    coverage = dict(report.get("coverage") or {})
    ratio = float(coverage.get("ratio") or 0.0)
    coverage["percent"] = round(ratio * 100, 1)
    findings = (report.get("validation") or {}).get("findings") or []
    spec_path = Path((report.get("artifacts") or {}).get("spec", ""))
    yaml_text = spec_path.read_text(encoding="utf-8") if spec_path.is_file() else ""
    return {
        "brief": brief_path.stem,
        "ok": bool((report.get("validation") or {}).get("ok")),
        "paths": stats.get("paths", 0),
        "operations": stats.get("operations", 0),
        "schemas": stats.get("schemas", 0),
        "coverage": coverage,
        "errors": [item for item in findings if item.get("severity") == "error"],
        "warnings": [item for item in findings if item.get("severity") == "warning"],
        "ambiguities": (report.get("enrichment") or {}).get("ambiguities") or [],
        "report": report,
        "yaml": yaml_text,
    }


def _prepare_target(target: Path) -> None:
    """Clear the target so a stale report can never answer for a failed run."""
    if target.exists():
        try:
            shutil.rmtree(target)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"output directory {target} cannot be cleared ({exc.strerror}); "
                    "fix its permissions or set SPECFORGE_WEB_OUT to a writable path"
                ),
            ) from exc
    try:
        target.mkdir(parents=True)
        probe = target / ".write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"output directory {target} is not writable ({exc.strerror}); "
                "fix its permissions or set SPECFORGE_WEB_OUT to a writable path"
            ),
        ) from exc


def _run_forge(brief_path: Path) -> dict[str, Any]:
    target = OUT_DIR / brief_path.stem
    _prepare_target(target)
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = forge_main(
            ["forge", "--brief", str(brief_path), "--out", str(target), "--offline", "--json"]
        )
    report_file = target / "forge_report.json"
    if code == 2 or not report_file.is_file():
        detail = stderr.getvalue().strip() or stdout.getvalue().strip() or "forge failed"
        raise HTTPException(status_code=422, detail=detail)
    report = json.loads(report_file.read_text(encoding="utf-8"))
    return _payload(brief_path, report)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", media_type="text/html")


@app.get("/api/briefs")
def briefs() -> dict[str, Any]:
    names = _brief_names()
    return {"briefs": names, "count": len(names)}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "briefs": len(_brief_names()),
        "out": str(OUT_DIR),
    }


@app.post("/api/forge")
def forge(request: ForgeRequest) -> dict[str, Any]:
    return _run_forge(_brief_path(request.brief))
