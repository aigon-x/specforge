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
