from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth import require_auth, require_media_auth
from app.database import get_db
from app.main import app


@pytest.fixture()
def guarded_client(db_session, monkeypatch):
    """启用真实鉴权的客户端：撤掉 conftest 里的默认放行。"""
    app.dependency_overrides.pop(require_auth, None)
    app.dependency_overrides.pop(require_media_auth, None)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_health_endpoint_stays_public(guarded_client):
    assert guarded_client.get("/health").status_code == 200


def test_without_configured_token_only_loopback_is_allowed(
    guarded_client, monkeypatch
):
    monkeypatch.delenv("APP_AUTH_TOKEN", raising=False)
    response = guarded_client.get("/api/review-tasks")
    # TestClient 的来源不是回环地址，所以应被拒绝，而不是悄悄放行。
    assert response.status_code == 403
    assert "APP_AUTH_TOKEN" in response.json()["detail"]


def test_configured_token_rejects_missing_and_wrong_token(
    guarded_client, monkeypatch
):
    monkeypatch.setenv("APP_AUTH_TOKEN", "unit-test-token")

    missing = guarded_client.get("/api/review-tasks")
    assert missing.status_code == 401

    wrong = guarded_client.get(
        "/api/review-tasks", headers={"X-API-Token": "nope"}
    )
    assert wrong.status_code == 401


def test_configured_token_accepts_header_and_bearer(guarded_client, monkeypatch):
    monkeypatch.setenv("APP_AUTH_TOKEN", "unit-test-token")

    by_header = guarded_client.get(
        "/api/review-tasks", headers={"X-API-Token": "unit-test-token"}
    )
    assert by_header.status_code == 200

    by_bearer = guarded_client.get(
        "/api/review-tasks",
        headers={"Authorization": "Bearer unit-test-token"},
    )
    assert by_bearer.status_code == 200


def test_media_endpoint_accepts_token_in_query(guarded_client, monkeypatch):
    monkeypatch.setenv("APP_AUTH_TOKEN", "unit-test-token")

    # 没有令牌时应被拒绝。
    assert guarded_client.get("/api/recordings/1/stream").status_code == 401

    # 带正确令牌时通过鉴权，随后因为录音不存在返回 404。
    allowed = guarded_client.get("/api/recordings/1/stream?token=unit-test-token")
    assert allowed.status_code == 404


def test_storage_directory_is_no_longer_public(guarded_client):
    # 原先 /storage 整目录公开挂载，任意录音都能被直接下载。
    assert guarded_client.get("/storage/recordings/1/a.m4a").status_code == 404
