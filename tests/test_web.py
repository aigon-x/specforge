"""HTTP surface of the SpecForge web UI."""

from __future__ import annotations

from fastapi.testclient import TestClient

from web.server import app

client = TestClient(app)


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


def test_index_is_navigable_from_the_keyboard():
    """Skip link, main landmark and a focusable result heading are the keyboard path."""
    html = client.get("/").text
    assert '<a class="skip" href="#main">' in html
    assert '<main id="main" tabindex="-1">' in html
    assert 'id="results-title" class="sr-only" tabindex="-1"' in html
    assert 'aria-live="polite"' in html          # the status region still announces
    assert 'id="results" aria-live' not in html  # results are announced by focus, not twice
