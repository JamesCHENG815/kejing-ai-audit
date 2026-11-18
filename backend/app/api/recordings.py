"""录音流式播放/下载。

原先 `main.py` 把整个 `storage/` 目录挂成公开静态目录，等于任何知道文件名的人
都能直接下载门店拜访录音。这里改为按记录 ID 提供，并统一走访问控制。
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import require_media_auth
from app.database import BACKEND_DIR, get_db
from app.models import Recording

router = APIRouter(
    prefix="/api/recordings",
    tags=["录音"],
    dependencies=[Depends(require_media_auth)],
)
DbSession = Annotated[Session, Depends(get_db)]

_MEDIA_TYPES = {
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
}


def _resolved_recording_path(stored_path: str) -> Path:
    candidate = Path(stored_path)
    path = candidate if candidate.is_absolute() else BACKEND_DIR / candidate
    resolved = path.resolve()
    # 库里的 file_path 是相对 backend/ 的路径；即使数据库被写坏，也不允许读到
    # backend 目录之外的文件。
    if not resolved.is_relative_to(BACKEND_DIR.resolve()):
        raise HTTPException(status_code=404, detail="录音文件不存在")
    return resolved


@router.get("/{recording_id}/stream")
def stream_recording(recording_id: int, db: DbSession):
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="录音不存在")
    path = _resolved_recording_path(recording.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="录音文件不存在")
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        filename=recording.original_filename,
        content_disposition_type="inline",
    )
