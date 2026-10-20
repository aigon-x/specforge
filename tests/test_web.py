"""HTTP surface of the SpecForge web UI."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import web.server as server
from web.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_out(tmp_path, monkeypatch):
    """Forge into a private directory: a shared out/ owned by another user must not score us."""
    monkeypatch.setattr(server, "OUT_DIR", tmp_path)
    return tmp_path


def test_index_returns_the_interface():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Forge contract" in response.text


def test_briefs_list_includes_shop():
    response = client.get("/api/briefs")
    assert response.status_code == 200
    assert "shop" in response.json()["briefs"]


def test_health_reports_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_forge_shop_covers_every_requirement():
    response = client.post("/api/forge", json={"brief": "shop"})
    assert response.status_code == 200
    body = response.json()
    assert body["coverage"]["percent"] == 100.0
    assert body["coverage"]["covered"] == body["coverage"]["total"]
    assert body["paths"] >= 1
    assert body["operations"] >= 1
    assert body["errors"] == []
    assert body["report"]["validation"]["ok"] is True
    assert body["yaml"].startswith("openapi:")


def test_unknown_brief_is_not_found():
    response = client.post("/api/forge", json={"brief": "../shop"})
    assert response.status_code == 404


def test_missing_brief_is_not_found():
    response = client.post("/api/forge", json={"brief": "does-not-exist"})
    assert response.status_code == 404


def test_unwritable_output_is_a_server_error_with_a_fixable_message(isolated_out):
    target = isolated_out / "shop"
    target.mkdir()
    (target / "stale.txt").write_text("old run", encoding="utf-8")
    target.chmod(0o555)
    try:
        response = client.post("/api/forge", json={"brief": "shop"})
    finally:
        target.chmod(0o755)
    assert response.status_code == 500, "a storage fault is not a bad brief (422)"
    detail = response.json()["detail"]
    assert "cannot be cleared" in detail or "not writable" in detail
    assert "SPECFORGE_WEB_OUT" in detail
    assert "Traceback" not in detail


def test_stale_output_is_replaced_not_merged(isolated_out):
    target = isolated_out / "shop"
    target.mkdir()
    (target / "forge_report.json").write_text('{"stale": true}', encoding="utf-8")
    response = client.post("/api/forge", json={"brief": "shop"})
    assert response.status_code == 200
    assert response.json()["coverage"]["percent"] == 100.0
    assert not (target / "stale.txt").exists()
    assert '"stale": true' not in (target / "forge_report.json").read_text(encoding="utf-8")


def test_index_is_navigable_from_the_keyboard():
    """Skip link, main landmark and a focusable result heading are the keyboard path."""
    html = client.get("/").text
    assert '<a class="skip" href="#main">' in html
    assert '<main id="main" tabindex="-1">' in html
    assert 'id="results-title" class="sr-only" tabindex="-1"' in html
    assert 'aria-live="polite"' in html          # the status region still announces
    assert 'id="results" aria-live' not in html  # results are announced by focus, not twice
