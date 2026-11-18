from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from app.services.import_service import save_upload


def _upload(content: bytes, filename: str = "拜访录音.m4a") -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=filename)


def test_save_upload_writes_full_content(tmp_path):
    destination = tmp_path / "batch" / "拜访录音.m4a"
    written = save_upload(_upload(b"audio-bytes"), destination, max_bytes=1024)

    assert written == len(b"audio-bytes")
    assert destination.read_bytes() == b"audio-bytes"


def test_save_upload_rejects_oversized_file(tmp_path):
    destination = tmp_path / "batch" / "超大录音.m4a"

    with pytest.raises(HTTPException) as excinfo:
        save_upload(_upload(b"x" * 4096), destination, max_bytes=1024)

    assert excinfo.value.status_code == 413
    # 半截文件必须清理掉，否则同名重传会撞 409 并白占磁盘。
    assert not destination.exists()
