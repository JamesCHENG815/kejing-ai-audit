from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import require_auth, require_media_auth
from app.database import Base
from app.main import app


@pytest.fixture(autouse=True)
def bypass_access_control():
    """业务测试默认跳过访问控制。

    TestClient 的 client.host 是 "testclient"，既不是回环地址也不带令牌，
    在真实的鉴权逻辑下会被拒绝。所以除 test_auth.py 之外的用例都走这层覆盖，
    鉴权本身由 test_auth.py 单独验证。
    """
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_media_auth] = lambda: None
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_media_auth, None)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
