from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    BatchCreatedResponse,
    BatchMatchesResponse,
    RecordingMatch,
    RecordingsUploadedResponse,
    SubmitBatchResponse,
    TaskMatch,
    UpdateMatchesRequest,
)
from app.services.import_service import (
    create_import_batch,
    delete_recording,
    load_batch_matches,
    submit_batch,
    update_matches,
    upload_recordings,
)
from app.services.analysis_service import analyze_submitted_batch


router = APIRouter(prefix="/api/import-batches", tags=["文件导入"])
DbSession = Annotated[Session, Depends(get_db)]


def matches_response(batch) -> BatchMatchesResponse:
    assigned_ids: set[int] = set()
    tasks: list[TaskMatch] = []
    for task in batch.tasks:
        recordings = []
        for link in task.task_recordings:
            assigned_ids.add(link.recording.id)
            recordings.append(
                RecordingMatch(
                    id=link.recording.id,
                    filename=link.recording.original_filename,
                    recommended=link.is_recommended,
                    confirmed=link.is_confirmed,
                )
            )
        tasks.append(
            TaskMatch(
                id=task.id,
                customer_id=task.customer_id,
                store_name=task.store_name,
                visitor=task.visitor,
                recordings=recordings,
            )
        )
    unassigned_recordings = [
        RecordingMatch(
            id=recording.id,
            filename=recording.original_filename,
            recommended=False,
            confirmed=False,
        )
        for recording in batch.recordings
        if recording.id not in assigned_ids
    ]
    return BatchMatchesResponse(
        batch_id=batch.id,
        status=batch.status,
        tasks=tasks,
        unassigned_recordings=unassigned_recordings,
    )


@router.post("", response_model=BatchCreatedResponse, status_code=201)
def create_batch(file: Annotated[UploadFile, File(...)], db: DbSession):
    batch = create_import_batch(db, file)
    return BatchCreatedResponse(
        id=batch.id,
        original_filename=batch.original_filename,
        status=batch.status,
        task_count=len(batch.tasks),
    )


@router.post("/{batch_id}/recordings", response_model=RecordingsUploadedResponse, status_code=201)
def create_recordings(
    batch_id: int,
    files: Annotated[list[UploadFile], File(...)],
    db: DbSession,
):
    uploaded_count, matched_count = upload_recordings(db, batch_id, files)
    return RecordingsUploadedResponse(
        batch_id=batch_id,
        uploaded_count=uploaded_count,
        matched_count=matched_count,
    )


@router.delete("/{batch_id}/recordings/{recording_id}", status_code=204)
def remove_recording(batch_id: int, recording_id: int, db: DbSession):
    delete_recording(db, batch_id, recording_id)


@router.get("/{batch_id}/matches", response_model=BatchMatchesResponse)
def get_matches(batch_id: int, db: DbSession):
    return matches_response(load_batch_matches(db, batch_id))


@router.put("/{batch_id}/matches", response_model=BatchMatchesResponse)
def put_matches(batch_id: int, payload: UpdateMatchesRequest, db: DbSession):
    update_matches(db, batch_id, payload.assignments)
    return matches_response(load_batch_matches(db, batch_id))


@router.post("/{batch_id}/submit", response_model=SubmitBatchResponse)
def submit(batch_id: int, background_tasks: BackgroundTasks, db: DbSession):
    task_count, recording_count = submit_batch(db, batch_id)
    background_tasks.add_task(analyze_submitted_batch, batch_id)
    return SubmitBatchResponse(
        batch_id=batch_id,
        status="submitted",
        task_count=task_count,
        recording_count=recording_count,
    )
