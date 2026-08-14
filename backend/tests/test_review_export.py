from urllib.parse import unquote

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from tests.test_analysis_service import create_pending_task


def test_task_export_uses_store_filename_and_only_exports_current_task(db_session):
    task, _ = create_pending_task(db_session)
    other, _ = create_pending_task(db_session)
    other.customer_id = "C-OTHER"
    other.store_name = "其他门店"
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/review-tasks/{task.id}/export")

        assert response.status_code == 200
        disposition = unquote(response.headers["content-disposition"])
        assert "测试门店_审核结果.csv" in disposition
        content = response.content.decode("utf-8-sig")
        assert task.customer_id in content
        assert "C-OTHER" not in content
    finally:
        app.dependency_overrides.clear()
