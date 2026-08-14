from __future__ import annotations

from collections import Counter
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.field_rules import (
    EvidenceValue,
    determine_field_status,
    is_auditable_field,
    required_audit_field_names,
)
from app.models import (
    AIFieldResult,
    AuditTask,
    ExcelFieldValue,
    HumanReview,
    TaskRecording,
)
from app.schemas import (
    ReviewEvidence,
    ReviewFieldResponse,
    ReviewHistoryResponse,
    ReviewRecordingResponse,
    ReviewStats,
    ReviewTaskDetailResponse,
    ReviewTaskResponse,
    ReviewTranscriptResponse,
    SaveReviewRequest,
)

FIELD_STATUSES = {"matched", "pending", "conflict", "missing"}
REVIEWABLE_TASK_STATUSES = {
    "pending_analysis",
    "analysis_failed",
    "pending",
    "reviewing",
    "completed",
}


def _text(value: str | None) -> str:
    return value if value not in (None, "") else "—"


def _field_status(
    excel: ExcelFieldValue | None, ai: AIFieldResult | None
) -> str:
    if ai and ai.status in FIELD_STATUSES:
        return ai.status
    if not ai:
        return "pending"
    evidence = None
    if ai.evidence_recording_id is not None:
        evidence = EvidenceValue(
            recording_id=ai.evidence_recording_id,
            start_seconds=ai.evidence_start_seconds or 0,
            end_seconds=ai.evidence_end_seconds or ai.evidence_start_seconds or 0,
            text=ai.evidence_text or "",
        )
    return determine_field_status(
        ai.field_name,
        excel.field_value if excel else None,
        ai.field_value,
        ai.confidence,
        evidence,
        excel_unit=excel.unit if excel else None,
        ai_unit=ai.unit,
    )


def _task_status(value: str) -> str:
    if value == "completed":
        return "completed"
    if value == "reviewing":
        return "reviewing"
    if value == "pending_analysis":
        return "analyzing"
    if value == "analysis_failed":
        return "analysis_failed"
    return "pending"


def _datetime_text(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def _load_tasks(db: Session) -> list[AuditTask]:
    statement = (
        select(AuditTask)
        .where(AuditTask.status.in_(REVIEWABLE_TASK_STATUSES))
        .options(
            selectinload(AuditTask.excel_values),
            selectinload(AuditTask.ai_results),
            selectinload(AuditTask.human_reviews),
            selectinload(AuditTask.task_recordings),
        )
        .order_by(AuditTask.updated_at.desc(), AuditTask.id.desc())
    )
    return list(db.scalars(statement).unique())


def _field_rows(task: AuditTask) -> list[ReviewFieldResponse]:
    excel_by_name = {
        item.field_name: item
        for item in task.excel_values
        if is_auditable_field(item.field_name)
    }
    ai_by_name = {
        item.field_name: item
        for item in task.ai_results
        if is_auditable_field(item.field_name)
    }
    review_by_name = {item.field_name: item for item in task.human_reviews}
    field_names = required_audit_field_names(
        task.created_at.year,
        [*excel_by_name, *ai_by_name],
    )

    rows: list[ReviewFieldResponse] = []
    for name in field_names:
        excel = excel_by_name.get(name)
        ai = ai_by_name.get(name)
        review = review_by_name.get(name)
        evidence = None
        if ai and ai.evidence_recording_id is not None:
            evidence = ReviewEvidence(
                recording_id=str(ai.evidence_recording_id),
                start=ai.evidence_start_seconds or 0,
                end=ai.evidence_end_seconds or ai.evidence_start_seconds or 0,
                text=ai.evidence_text or "",
            )
        initial_value = (
            ai.field_value
            if ai and ai.field_value not in (None, "")
            else excel.field_value if excel else None
        )
        rows.append(
            ReviewFieldResponse(
                key=name,
                label=name,
                excel=_text(excel.field_value if excel else None),
                ai=_text(ai.field_value if ai else None),
                unit=(ai.unit if ai and ai.unit else excel.unit if excel else None),
                confidence=ai.confidence if ai and ai.confidence is not None else 0,
                status=_field_status(excel, ai),
                final=_text(review.final_value if review else initial_value),
                reason=review.change_reason or "" if review else "",
                confirmed=review.confirmed if review else False,
                evidence=evidence,
            )
        )
    return rows


def _task_response(task: AuditTask) -> ReviewTaskResponse:
    counts = Counter(field.status for field in _field_rows(task))
    excel_values = {item.field_name: item.field_value for item in task.excel_values}
    address = excel_values.get("地址") or excel_values.get("POI_ADDRESS") or "—"
    visit_date = excel_values.get("拜访时间") or excel_values.get("拜访日期") or "—"
    if visit_date != "—":
        visit_date = visit_date.split("T", 1)[0]
    return ReviewTaskResponse(
        id=str(task.id),
        batch_id=task.import_batch_id,
        customer_id=task.customer_id,
        store=task.store_name,
        visitor=task.visitor,
        status=_task_status(task.status),
        has_recording=bool(task.task_recordings),
        updated_at=_datetime_text(task.updated_at),
        stats=ReviewStats(**{name: counts[name] for name in FIELD_STATUSES}),
        address=address,
        visit_date=visit_date,
    )


def list_review_tasks(db: Session) -> list[ReviewTaskResponse]:
    return [_task_response(task) for task in _load_tasks(db)]


def load_review_task(db: Session, task_id: int) -> AuditTask:
    from app.models import Recording

    statement = (
        select(AuditTask)
        .where(AuditTask.id == task_id)
        .options(
            selectinload(AuditTask.excel_values),
            selectinload(AuditTask.ai_results),
            selectinload(AuditTask.human_reviews),
            selectinload(AuditTask.task_recordings)
            .selectinload(TaskRecording.recording)
            .selectinload(Recording.transcript_segments),
        )
    )
    task = db.scalar(statement)
    if task is None or task.status not in REVIEWABLE_TASK_STATUSES:
        raise HTTPException(status_code=404, detail="审核任务不存在")
    return task


def review_task_detail(db: Session, task_id: int) -> ReviewTaskDetailResponse:
    task = load_review_task(db, task_id)
    recordings = [link.recording for link in task.task_recordings]
    evidence_segments = {
        (
            item.evidence_recording_id,
            item.evidence_start_seconds,
            item.evidence_end_seconds,
        )
        for item in task.ai_results
        if item.evidence_recording_id is not None
    }
    transcripts = [
        ReviewTranscriptResponse(
            recording_id=str(recording.id),
            time=segment.start_seconds,
            speaker=segment.speaker or "未知说话人",
            text=segment.text,
            evidence=(
                recording.id,
                segment.start_seconds,
                segment.end_seconds,
            ) in evidence_segments,
        )
        for recording in recordings
        for segment in sorted(recording.transcript_segments, key=lambda item: item.start_seconds)
    ]
    history = []
    if task.ai_results:
        latest_ai = max(item.updated_at for item in task.ai_results)
        history.append(
            ReviewHistoryResponse(
                who="AI 系统", when=_datetime_text(latest_ai), action="完成录音字段提取与风险比对"
            )
        )
    for review in sorted(task.human_reviews, key=lambda item: item.updated_at, reverse=True):
        history.append(
            ReviewHistoryResponse(
                who=review.reviewer or "当前经理",
                when=_datetime_text(review.updated_at),
                action=f"{'确认' if review.confirmed else '保存'}字段：{review.field_name}",
            )
        )
    return ReviewTaskDetailResponse(
        task=_task_response(task),
        fields=_field_rows(task),
        recordings=[
            ReviewRecordingResponse(
                id=str(recording.id),
                name=recording.original_filename,
                duration=recording.duration_seconds or 0,
                url=f"/{recording.file_path}",
            )
            for recording in recordings
        ],
        transcripts=transcripts,
        history=history,
        has_ai_analysis=bool(task.ai_results),
        has_transcript=bool(transcripts),
    )


def save_review(
    db: Session, task_id: int, payload: SaveReviewRequest, *, submit: bool
) -> tuple[AuditTask, int, int]:
    task = load_review_task(db, task_id)
    actual_fields = {field.key: field for field in _field_rows(task)}
    submitted_fields = {field.key: field for field in payload.fields}
    unknown = submitted_fields.keys() - actual_fields.keys()
    if unknown:
        raise HTTPException(status_code=422, detail=f"未知审核字段：{', '.join(sorted(unknown))}")
    if submit and submitted_fields.keys() != actual_fields.keys():
        raise HTTPException(status_code=422, detail="提交审核时必须包含全部字段")

    existing = {item.field_name: item for item in task.human_reviews}
    for key, field in submitted_fields.items():
        original = actual_fields[key]
        if field.confirmed and field.final != original.excel and not field.reason.strip():
            raise HTTPException(status_code=422, detail=f"“{original.label}”修改了原值，请填写修改原因")
        review = existing.get(key)
        if review is None:
            review = HumanReview(task=task, field_name=key)
            db.add(review)
        review.final_value = None if field.final == "—" else field.final
        review.unit = original.unit
        review.change_reason = field.reason.strip() or None
        review.reviewer = payload.reviewer.strip() or "当前经理"
        review.confirmed = field.confirmed

    confirmed_count = sum(field.confirmed for field in payload.fields)
    if submit:
        if confirmed_count != len(actual_fields):
            raise HTTPException(status_code=409, detail="仍有字段未确认")
        task.status = "completed"
    elif task.status != "completed":
        task.status = "reviewing"
    db.commit()
    db.refresh(task)
    return task, confirmed_count, len(actual_fields)
