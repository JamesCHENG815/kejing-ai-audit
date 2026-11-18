"""审核留痕：每次保存/提交都要在 review_events 里留下可追溯的记录。

设计约束（改代码前先读这里）：
- ``HumanReview`` 只存"当前值"，覆盖写会丢历史；``ReviewEvent`` 是 append-only。
- 只有"值真的变了 / 只有原因变了"才写字段事件，避免每次保存刷 47 条噪声。
- 每次保存和提交各写一条会话事件，即使一个字段都没改。
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import AIFieldResult, ReviewEvent
from app.schemas import ReviewFieldInput, SaveReviewRequest
from app.services.review_service import (
    EVENT_FIELD_CHANGE,
    EVENT_FIELD_REASON,
    EVENT_SAVE,
    EVENT_SUBMIT,
    review_task_detail,
    save_review,
)
from tests.test_analysis_service import create_pending_task


def _request(detail, *, change=None, confirm_all=False, reviewer="当前经理"):
    """Build a save payload from the current detail, optionally changing one field."""
    fields = []
    for field in detail.fields:
        final, reason = field.final, field.reason
        if change and field.key == change[0]:
            final, reason = change[1], change[2]
        fields.append(
            ReviewFieldInput(
                key=field.key, final=final, reason=reason, confirmed=confirm_all
            )
        )
    return SaveReviewRequest(fields=fields, reviewer=reviewer)


def _events(db_session, task_id, event_type=None):
    statement = select(ReviewEvent).where(ReviewEvent.task_id == task_id)
    if event_type is not None:
        statement = statement.where(ReviewEvent.event_type == event_type)
    return list(db_session.scalars(statement.order_by(ReviewEvent.id)))


def test_first_draft_save_without_edits_writes_only_the_session_event(db_session):
    task, _ = create_pending_task(db_session)
    detail = review_task_detail(db_session, task.id)

    save_review(db_session, task.id, _request(detail), submit=False)

    assert _events(db_session, task.id, EVENT_FIELD_CHANGE) == []
    session_events = _events(db_session, task.id, EVENT_SAVE)
    assert len(session_events) == 1
    # 一个都没确认，字段总数是 47。
    assert session_events[0].value_after == f"0/{len(detail.fields)}"


def test_value_edit_records_before_and_after(db_session):
    task, _ = create_pending_task(db_session)
    detail = review_task_detail(db_session, task.id)
    target = next(
        field for field in detail.fields if field.key.startswith("马爹利上一个自然年")
    )
    assert target.excel == "20"

    save_review(
        db_session,
        task.id,
        _request(detail, change=(target.key, "26", "录音里说的是二十六万")),
        submit=False,
    )

    changes = _events(db_session, task.id, EVENT_FIELD_CHANGE)
    assert len(changes) == 1
    event = changes[0]
    assert event.field_name == target.key
    assert event.value_before == "20"
    assert event.value_after == "26"
    assert event.reason == "录音里说的是二十六万"
    assert event.reviewer == "当前经理"


def test_reason_only_edit_uses_its_own_event_type(db_session):
    task, _ = create_pending_task(db_session)
    detail = review_task_detail(db_session, task.id)
    target = next(
        field for field in detail.fields if field.key.startswith("马爹利上一个自然年")
    )

    save_review(
        db_session,
        task.id,
        _request(detail, change=(target.key, "20", "补充说明：店长口述")),
        submit=False,
    )

    assert _events(db_session, task.id, EVENT_FIELD_CHANGE) == []
    reasons = _events(db_session, task.id, EVENT_FIELD_REASON)
    assert len(reasons) == 1
    assert reasons[0].field_name == target.key
    assert reasons[0].value_after == "20"


def test_saving_the_same_value_twice_does_not_duplicate_the_event(db_session):
    task, _ = create_pending_task(db_session)
    detail = review_task_detail(db_session, task.id)
    target = next(
        field for field in detail.fields if field.key.startswith("马爹利上一个自然年")
    )

    save_review(
        db_session, task.id, _request(detail, change=(target.key, "26", "改")), submit=False
    )
    detail = review_task_detail(db_session, task.id)
    save_review(
        db_session, task.id, _request(detail, change=(target.key, "26", "改")), submit=False
    )

    changes = _events(db_session, task.id, EVENT_FIELD_CHANGE)
    assert [(item.value_before, item.value_after) for item in changes] == [("20", "26")]
    assert len(_events(db_session, task.id, EVENT_SAVE)) == 2


def test_second_edit_keeps_the_first_one(db_session):
    """覆盖写的旧实现会丢掉第一次修改；事件表必须都留着。"""
    task, _ = create_pending_task(db_session)
    detail = review_task_detail(db_session, task.id)
    target = next(
        field for field in detail.fields if field.key.startswith("马爹利上一个自然年")
    )

    save_review(
        db_session, task.id, _request(detail, change=(target.key, "26", "第一次")), submit=False
    )
    detail = review_task_detail(db_session, task.id)
    save_review(
        db_session, task.id, _request(detail, change=(target.key, "31", "第二次")), submit=False
    )

    changes = _events(db_session, task.id, EVENT_FIELD_CHANGE)
    assert [(item.value_before, item.value_after) for item in changes] == [
        ("20", "26"),
        ("26", "31"),
    ]
    assert [item.reason for item in changes] == ["第一次", "第二次"]


def test_reviewer_is_recorded_per_save(db_session):
    task, _ = create_pending_task(db_session)
    detail = review_task_detail(db_session, task.id)

    save_review(db_session, task.id, _request(detail, reviewer="  李经理 "), submit=False)

    assert _events(db_session, task.id, EVENT_SAVE)[0].reviewer == "李经理"


def test_default_reviewer_when_blank(db_session):
    task, _ = create_pending_task(db_session)
    detail = review_task_detail(db_session, task.id)

    save_review(db_session, task.id, _request(detail, reviewer="   "), submit=False)

    assert _events(db_session, task.id, EVENT_SAVE)[0].reviewer == "当前经理"


def test_submit_records_confirmed_counts(db_session):
    task, _ = create_pending_task(db_session)
    detail = review_task_detail(db_session, task.id)

    save_review(db_session, task.id, _request(detail, confirm_all=True), submit=True)

    submits = _events(db_session, task.id, EVENT_SUBMIT)
    assert len(submits) == 1
    assert submits[0].value_after == f"{len(detail.fields)}/{len(detail.fields)}"
    assert task.status == "completed"


def test_detail_history_reads_from_events_not_current_state(db_session):
    task, _ = create_pending_task(db_session)
    detail = review_task_detail(db_session, task.id)
    target = next(
        field for field in detail.fields if field.key.startswith("马爹利上一个自然年")
    )

    save_review(
        db_session,
        task.id,
        _request(detail, change=(target.key, "26", "录音里说的是二十六万")),
        submit=False,
    )
    detail = review_task_detail(db_session, task.id)

    # 倒序：保存动作在字段修改之后写入，所以排在更前面。
    assert [item.kind for item in detail.history] == ["save", "change"]
    change = detail.history[1]
    assert change.field == target.key
    assert change.before == "20"
    assert change.after == "26"
    assert change.reason == "录音里说的是二十六万"
    assert "20" in change.action and "26" in change.action


def test_history_puts_the_ai_entry_last(db_session):
    task, _ = create_pending_task(db_session)
    task.ai_results.append(
        AIFieldResult(
            field_name="团购客户有多少个(经常拿1箱以上任何酒)",
            field_value="3",
            status="matched",
            confidence=0.9,
        )
    )
    db_session.commit()
    detail = review_task_detail(db_session, task.id)

    save_review(db_session, task.id, _request(detail), submit=False)
    detail = review_task_detail(db_session, task.id)

    assert detail.has_ai_analysis is True
    # AI 分析是最早发生的一条，倒序排列时落在最后。
    assert detail.history[-1].kind == "ai"
    assert detail.history[0].kind == "save"


def test_missing_reason_still_rejected_before_any_event_is_written(db_session):
    task, _ = create_pending_task(db_session)
    detail = review_task_detail(db_session, task.id)
    target = next(
        field for field in detail.fields if field.key.startswith("马爹利上一个自然年")
    )
    payload = _request(detail)
    for field in payload.fields:
        if field.key == target.key:
            field.final = "26"
            field.confirmed = True
            field.reason = ""

    with pytest.raises(HTTPException) as info:
        save_review(db_session, task.id, payload, submit=False)

    assert info.value.status_code == 422
    db_session.rollback()
    assert _events(db_session, task.id) == []
