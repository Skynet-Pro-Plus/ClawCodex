from __future__ import annotations

from fastapi.testclient import TestClient

from src.server.app import create_app


def test_local_api_token_is_enforced_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("CLAWCODEX_API_TOKEN", "test-token")
    client = TestClient(create_app())

    assert client.get("/api/tasks").status_code == 401
    assert client.get("/api/tasks", headers={"x-clawcodex-token": "test-token"}).status_code == 200


def test_local_origin_is_required_when_origin_header_is_present(monkeypatch) -> None:
    monkeypatch.setenv("CLAWCODEX_API_TOKEN", "test-token")
    client = TestClient(create_app())

    response = client.get(
        "/api/tasks",
        headers={"x-clawcodex-token": "test-token", "origin": "https://evil.example"},
    )

    assert response.status_code == 403
