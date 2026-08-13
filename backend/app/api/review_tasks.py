import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    ReviewTaskDetailResponse,
    ReviewTaskResponse,
    SaveReviewRequest,
    SaveReviewResponse,
)
from app.services.review_service import (
    list_review_tasks,
    review_task_detail,
    save_review,
)

router = APIRouter(prefix="/api/review-tasks", tags=["经理审核"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[ReviewTaskResponse])
def get_review_tasks(db: DbSession):
    return list_review_tasks(db)


@router.get("/export")
def export_review_tasks(db: DbSession):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(
        [
            "批次ID", "任务ID", "门店ID", "门店名称", "拜访人", "字段名称",
            "原始Excel值", "AI识别值", "最终人工值", "修改原因", "字段审核状态",
            "任务状态", "更新时间",
        ]
    )
    for task in list_review_tasks(db):
        detail = review_task_detail(db, int(task.id))
        for field in detail.fields:
            writer.writerow(
                [
                    task.batch_id, task.id, task.customer_id, task.store, task.visitor,
                    field.label, field.excel, field.ai, field.final, field.reason,
                    field.status, task.status, task.updated_at,
                ]
            )
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = (
        'attachment; filename="kejing-audit-review-results.csv"'
    )
    return response


@router.get("/{task_id}", response_model=ReviewTaskDetailResponse)
def get_review_task(task_id: int, db: DbSession):
    return review_task_detail(db, task_id)


@router.put("/{task_id}/draft", response_model=SaveReviewResponse)
def put_review_draft(task_id: int, payload: SaveReviewRequest, db: DbSession):
    task, confirmed_count, field_count = save_review(
        db, task_id, payload, submit=False
    )
    return SaveReviewResponse(
        task_id=str(task.id), status="reviewing", confirmed_count=confirmed_count,
        field_count=field_count,
    )


@router.post("/{task_id}/submit", response_model=SaveReviewResponse)
def submit_review(task_id: int, payload: SaveReviewRequest, db: DbSession):
    task, confirmed_count, field_count = save_review(
        db, task_id, payload, submit=True
    )
    return SaveReviewResponse(
        task_id=str(task.id), status="completed", confirmed_count=confirmed_count,
        field_count=field_count,
    )
