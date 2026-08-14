import re
import shutil
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, BinaryIO

from fastapi import HTTPException, UploadFile, status
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import BACKEND_DIR
from app.field_rules import is_auditable_field, is_image_field
from app.models import (
    AuditTask,
    ExcelFieldValue,
    ImportBatch,
    Recording,
    TaskRecording,
)


IMPORTS_DIR = BACKEND_DIR / "storage" / "imports"
RECORDINGS_DIR = BACKEND_DIR / "storage" / "recordings"
EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".aac", ".flac"}


def safe_filename(filename: str | None, fallback: str) -> str:
    name = Path(filename or fallback).name.strip()
    return name or fallback


def save_upload(upload: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    upload.file.seek(0)
    with destination.open("wb") as target:
        shutil.copyfileobj(upload.file, target)


def _cell_text(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def parse_visit_excel(file: BinaryIO) -> list[dict[str, Any]]:
    try:
        workbook = load_workbook(file, read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"无法读取 Excel 文件：{exc}") from exc

    if "拜访数据" not in workbook.sheetnames:
        workbook.close()
        raise HTTPException(status_code=422, detail="Excel 中缺少“拜访数据”工作表")

    sheet = workbook["拜访数据"]
    rows = sheet.iter_rows(values_only=True)
    headers = [str(value).strip() if value is not None else "" for value in next(rows, ())]
    required = {"POI_ID", "门店名称", "拜访人"}
    missing = required - set(headers)
    if missing:
        workbook.close()
        raise HTTPException(status_code=422, detail=f"Excel 缺少字段：{', '.join(sorted(missing))}")

    visits: list[dict[str, Any]] = []
    for values in rows:
        row = dict(zip(headers, values, strict=False))
        # Excel 中常会有格式留下的空白行；跳过它而不是停止读取，避免漏掉后续门店。
        if not any(value is not None for value in values):
            continue
        customer_id = _cell_text(row.get("POI_ID"))
        store_name = _cell_text(row.get("门店名称"))
        visitor = _cell_text(row.get("拜访人"))
        if (
            not customer_id
            or not customer_id.strip()
            or not store_name
            or not store_name.strip()
            or not visitor
            or not visitor.strip()
        ):
            continue
        visits.append(
            {
                "customer_id": customer_id,
                "store_name": store_name,
                "visitor": visitor,
                "fields": {
                    header: _cell_text(row.get(header))
                    for header in headers
                    if header
                    and not is_image_field(header)
                    and (
                        row.get(header) is not None
                        or is_auditable_field(header)
                    )
                },
            }
        )
    workbook.close()

    if not visits:
        raise HTTPException(status_code=422, detail="未在“拜访数据”中找到有效门店")
    return visits


def create_import_batch(db: Session, upload: UploadFile) -> ImportBatch:
    filename = safe_filename(upload.filename, "拜访数据.xlsx")
    if Path(filename).suffix.lower() not in EXCEL_SUFFIXES:
        raise HTTPException(status_code=415, detail="仅支持 .xlsx 或 .xlsm 文件")

    batch = ImportBatch(original_filename=filename, file_path="", status="parsing")
    db.add(batch)
    db.flush()
    destination = IMPORTS_DIR / str(batch.id) / filename

    try:
        save_upload(upload, destination)
        with destination.open("rb") as source:
            visits = parse_visit_excel(source)

        batch.file_path = str(destination.relative_to(BACKEND_DIR))
        for visit in visits:
            task = AuditTask(
                import_batch=batch,
                customer_id=visit["customer_id"],
                store_name=visit["store_name"],
                visitor=visit["visitor"],
                status="matching",
            )
            task.excel_values = [
                ExcelFieldValue(field_name=name, field_value=value)
                for name, value in visit["fields"].items()
            ]
            db.add(task)
        batch.status = "matching"
        db.commit()
        db.refresh(batch)
        return batch
    except Exception:
        db.rollback()
        if destination.exists():
            destination.unlink()
        raise


def _normalize_name(value: str) -> str:
    value = Path(value).stem.lower()
    value = re.sub(r"[（(]\d+[）)]$", "", value)
    value = re.sub(r"录音信息|洋酒|市場|市场|调研|烟酒行|烟酒|酒业|商行|店", "", value)
    value = re.sub(r"[\s\-_()（）\[\]【】.,，]+", "", value)
    return value.replace("珍", "真")


def recommend_task(filename: str, tasks: list[AuditTask]) -> AuditTask | None:
    audio_name = _normalize_name(filename)
    best_task: AuditTask | None = None
    best_score = 0.0
    for task in tasks:
        store_name = _normalize_name(task.store_name)
        score = SequenceMatcher(None, audio_name, store_name).ratio()
        if audio_name in store_name or store_name in audio_name:
            score = max(score, 0.95)
        if score > best_score:
            best_score, best_task = score, task
    return best_task if best_score >= 0.42 else None


def get_batch(db: Session, batch_id: int) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    return batch


def upload_recordings(
    db: Session, batch_id: int, uploads: list[UploadFile]
) -> tuple[int, int]:
    batch = get_batch(db, batch_id)
    tasks = list(db.scalars(select(AuditTask).where(AuditTask.import_batch_id == batch.id)))
    if not uploads:
        raise HTTPException(status_code=422, detail="请至少上传一段录音")

    uploaded_count = 0
    matched_count = 0
    created_paths: list[Path] = []
    try:
        for upload in uploads:
            filename = safe_filename(upload.filename, f"recording-{uploaded_count + 1}.m4a")
            if Path(filename).suffix.lower() not in AUDIO_SUFFIXES:
                raise HTTPException(status_code=415, detail=f"不支持的录音格式：{filename}")
            destination = RECORDINGS_DIR / str(batch.id) / filename
            if destination.exists():
                raise HTTPException(status_code=409, detail=f"录音已存在：{filename}")
            save_upload(upload, destination)
            created_paths.append(destination)
            recording = Recording(
                import_batch=batch,
                original_filename=filename,
                file_path=str(destination.relative_to(BACKEND_DIR)),
                status="uploaded",
            )
            db.add(recording)
            db.flush()
            recommended_task = recommend_task(filename, tasks)
            if recommended_task:
                db.add(
                    TaskRecording(
                        task=recommended_task,
                        recording=recording,
                        is_recommended=True,
                        is_confirmed=False,
                    )
                )
                matched_count += 1
            uploaded_count += 1
        batch.status = "matching"
        db.commit()
        return uploaded_count, matched_count
    except Exception:
        db.rollback()
        for path in created_paths:
            if path.exists():
                path.unlink()
        raise


def delete_recording(db: Session, batch_id: int, recording_id: int) -> None:
    batch = get_batch(db, batch_id)
    if batch.status == "submitted":
        raise HTTPException(status_code=409, detail="已提交批次不能删除录音")
    recording = db.scalar(
        select(Recording).where(
            Recording.id == recording_id,
            Recording.import_batch_id == batch_id,
        )
    )
    if recording is None:
        raise HTTPException(status_code=404, detail="录音不存在")
    path = BACKEND_DIR / recording.file_path
    db.delete(recording)
    db.commit()
    if path.exists():
        path.unlink()


def load_batch_matches(db: Session, batch_id: int) -> ImportBatch:
    statement = (
        select(ImportBatch)
        .where(ImportBatch.id == batch_id)
        .options(
            selectinload(ImportBatch.tasks)
            .selectinload(AuditTask.task_recordings)
            .selectinload(TaskRecording.recording),
            selectinload(ImportBatch.recordings),
        )
    )
    batch = db.scalar(statement)
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    return batch


def update_matches(db: Session, batch_id: int, assignments) -> None:
    batch = load_batch_matches(db, batch_id)
    task_ids = {task.id for task in batch.tasks}
    recording_ids = {recording.id for recording in batch.recordings}
    assigned_recording_ids: set[int] = set()
    for assignment in assignments:
        if assignment.recording_id in assigned_recording_ids:
            raise HTTPException(
                status_code=422,
                detail=f"录音 {assignment.recording_id} 在一次提交中被重复关联",
            )
        assigned_recording_ids.add(assignment.recording_id)
        if assignment.task_id not in task_ids:
            raise HTTPException(
                status_code=422,
                detail=f"任务 {assignment.task_id} 不属于当前批次",
            )
        if assignment.recording_id not in recording_ids:
            raise HTTPException(
                status_code=422,
                detail=f"录音 {assignment.recording_id} 不属于当前批次",
            )

        links = [
            link
            for task in batch.tasks
            for link in task.task_recordings
            if link.recording_id == assignment.recording_id
        ]
        if links:
            link = links[0]
            link.task_id = assignment.task_id
            link.is_confirmed = assignment.confirmed
            # 一段录音只能归属一个门店。清除遗留的重复关联，保持提交校验准确。
            for duplicate_link in links[1:]:
                db.delete(duplicate_link)
        else:
            db.add(
                TaskRecording(
                    task_id=assignment.task_id,
                    recording_id=assignment.recording_id,
                    is_recommended=False,
                    is_confirmed=assignment.confirmed,
                )
            )
    db.commit()


def submit_batch(db: Session, batch_id: int) -> tuple[int, int]:
    batch = load_batch_matches(db, batch_id)
    links = [link for task in batch.tasks for link in task.task_recordings]
    if not links:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="尚未上传录音")
    linked_recording_ids = {link.recording_id for link in links}
    if len(links) != len(batch.recordings) or len(linked_recording_ids) != len(batch.recordings):
        raise HTTPException(status_code=409, detail="仍有录音未关联门店")
    unconfirmed = [link.id for link in links if not link.is_confirmed]
    if unconfirmed:
        raise HTTPException(status_code=409, detail="请先确认所有录音关联")
    for task in batch.tasks:
        # 只有关联了录音的门店需要进入 AI 分析；无录音门店仍可进入人工审核。
        task.status = "pending_analysis" if task.task_recordings else "pending"
    for link in links:
        link.recording.status = "queued"
    batch.status = "submitted"
    db.commit()
    return len(batch.tasks), len(links)
