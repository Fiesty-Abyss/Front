import pytest
from fastapi.testclient import TestClient

from front_api import main


@pytest.fixture
def spa_client(data_dir, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "static").mkdir(parents=True)
    (dist / "index.html").write_text("<h1>Front</h1>", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("private-marker", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)
    with TestClient(main.create_app()) as client:
        yield client


def test_spa_cannot_serve_files_outside_dist(spa_client):
    for path in ("/%2e%2e/outside.txt", "/%2e%2e%2foutside.txt", "/%2e%2e%5coutside.txt"):
        response = spa_client.get(path)
        assert response.status_code == 404
        assert "private-marker" not in response.text


def test_spa_fallback_preserves_routes_but_not_unknown_apis(spa_client):
    assert spa_client.get("/notes/12").text == "<h1>Front</h1>"
    assert spa_client.get("/favicon.svg").text == "<svg/>"
    for path in ("/api", "/api/not-a-real-route"):
        response = spa_client.get(path)
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
