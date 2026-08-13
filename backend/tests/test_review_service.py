from app.models import TranscriptSegment
from app.services.review_service import review_task_detail
from tests.test_analysis_service import create_pending_task


def test_review_detail_includes_store_metadata_and_analysis_flags(db_session):
    task, recording = create_pending_task(db_session)
    task.excel_values.extend(
        [
            type(task.excel_values[0])(
                field_name="地址", field_value="广东省广州市测试路1号"
            ),
            type(task.excel_values[0])(
                field_name="拜访时间", field_value="2026-08-11T00:00:00"
            ),
        ]
    )
    recording.transcript_segments = [
        TranscriptSegment(
            start_seconds=1,
            end_seconds=2,
            speaker="门店",
            text="测试转写",
        )
    ]
    db_session.commit()

    detail = review_task_detail(db_session, task.id)

    assert detail.task.address == "广东省广州市测试路1号"
    assert detail.task.visit_date == "2026-08-11"
    assert detail.has_transcript is True
    assert detail.has_ai_analysis is False
    assert all("图片" not in field.key for field in detail.fields)


def test_review_detail_reports_missing_transcript_and_ai(db_session):
    task, _recording = create_pending_task(db_session)

    detail = review_task_detail(db_session, task.id)

    assert detail.has_transcript is False
    assert detail.has_ai_analysis is False
