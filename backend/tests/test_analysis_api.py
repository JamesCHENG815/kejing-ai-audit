from fastapi.testclient import TestClient

from app.api import review_tasks
from app.database import get_db
from app.main import app
from app.models import AuditTask
from app.services.analysis_service import ExtractedFieldData, TranscribedSegmentData
from tests.test_analysis_service import LAST_YEAR, create_pending_task


class ApiFakeProvider:
    def transcribe(self, _path):
        return [TranscribedSegmentData(1, 3, "门店", "去年马爹利二十万。")]

    def extract_fields(self, _targets, _transcript):
        return [ExtractedFieldData(LAST_YEAR, "20", "万元", 0.95, 1, 0)]


def test_analyze_task_endpoint_persists_real_provider_output(db_session, monkeypatch):
    task, _recording = create_pending_task(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    monkeypatch.setattr(review_tasks, "_provider", lambda: ApiFakeProvider())
    try:
        with TestClient(app) as client:
            response = client.post(f"/api/review-tasks/{task.id}/analyze", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["task_id"] == task.id
        assert body["transcript_segment_count"] == 1
        assert body["ai_result_count"] == 47
        assert body["matched"] == 1
        assert body["missing"] == 46
    finally:
        app.dependency_overrides.clear()


def test_analyze_endpoint_requires_openai_key(db_session, monkeypatch):
    task, _recording = create_pending_task(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        with TestClient(app) as client:
            response = client.post(f"/api/review-tasks/{task.id}/analyze", json={})
        assert response.status_code == 503
        assert "OPENAI_API_KEY" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_analyze_pending_endpoint_processes_pending_tasks(db_session, monkeypatch):
    first, _ = create_pending_task(db_session)
    second, _ = create_pending_task(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    monkeypatch.setattr(review_tasks, "_provider", lambda: ApiFakeProvider())
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/review-tasks/analyze-pending", json={"limit": 1}
            )
        assert response.status_code == 200
        body = response.json()
        assert body["requested_count"] == 1
        assert body["completed_count"] == 1
        assert body["results"][0]["task_id"] == first.id
        assert db_session.get(AuditTask, first.id).status == "pending"
        assert db_session.get(AuditTask, second.id).status == "pending_analysis"
    finally:
        app.dependency_overrides.clear()


def test_analyze_pending_endpoint_can_be_scoped_to_batch(db_session, monkeypatch):
    first, _ = create_pending_task(db_session)
    second, _ = create_pending_task(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    monkeypatch.setattr(review_tasks, "_provider", lambda: ApiFakeProvider())
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/review-tasks/analyze-pending",
                json={"limit": 100, "batch_id": second.import_batch_id},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["requested_count"] == 1
        assert body["results"][0]["task_id"] == second.id
        assert db_session.get(AuditTask, first.id).status == "pending_analysis"
        assert db_session.get(AuditTask, second.id).status == "pending"
    finally:
        app.dependency_overrides.clear()
