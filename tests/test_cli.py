import json
from pathlib import Path

import yaml

from specforge import parse_brief
from specforge.cli import main
from specforge.generator import generate_spec

from conftest import minimal_brief

ROOT = Path(__file__).resolve().parents[1]
BRIEF = ROOT / "briefs" / "shop.yaml"


def test_forge_offline_end_to_end(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["forge", "--brief", str(BRIEF), "--out", str(out), "--offline"]) == 0
    stdout = capsys.readouterr().out
    assert "OFFLINE" in stdout
    spec_path = out / "openapi.yaml"
    report_path = out / "forge_report.json"
    assert spec_path.exists() and report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["enrichment"]["mode"] == "offline"
    assert report["validation"]["errors"] == 0
    assert report["coverage"]["ratio"] == 1.0
    assert report["artifacts"]["contract_tests_count"] == 45
    assert (out / "contract_tests" / "test_contract_shop.py").exists()
    assert main(["verify", str(spec_path), "--brief", str(BRIEF), "--json"]) == 0


def test_forge_live_without_key_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    code = main(["forge", "--brief", str(BRIEF), "--out", str(tmp_path), "--live"])
    assert code == 2
    assert "NEBIUS_API_KEY" in capsys.readouterr().err


def test_forge_rejects_brief_without_requirements(tmp_path, capsys):
    payload = minimal_brief()
    payload["requirements"] = []
    brief_path = tmp_path / "broken.yaml"
    brief_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    code = main(["forge", "--brief", str(brief_path), "--out", str(tmp_path / "out"), "--offline"])
    assert code == 2
    assert "requirements" in capsys.readouterr().err


def test_verify_detects_invalid_document(tmp_path, capsys):
    path = tmp_path / "broken.yaml"
    path.write_text(
        yaml.safe_dump({"openapi": "3.0.3", "info": {"title": "X", "version": "1"}, "paths": {}}),
        encoding="utf-8",
    )
    assert main(["verify", str(path)]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_verify_strict_fails_on_warning(tmp_path, capsys):
    spec = generate_spec(parse_brief(minimal_brief()))
    spec["components"]["securitySchemes"] = {
        "unused": {"type": "http", "scheme": "bearer"}
    }
    path = tmp_path / "warn.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    assert main(["verify", str(path)]) == 0
    capsys.readouterr()
    assert main(["verify", str(path), "--strict"]) == 1
    assert "SEC-UNUSED-SCHEME" in capsys.readouterr().out


def test_forge_json_output_is_machine_readable(tmp_path, capsys):
    code = main([
        "forge", "--brief", str(BRIEF), "--out", str(tmp_path / "out"),
        "--offline", "--no-enrich", "--json",
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tool"] == "specforge"
    assert payload["enrichment"]["mode"] == "disabled"
    assert payload["stats"]["paths"] == 6
