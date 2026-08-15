from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from app.database import BACKEND_DIR


load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class AnalysisSettings:
    openai_api_key: str | None
    transcription_model: str
    extraction_model: str
    confidence_threshold: float
    audio_chunk_seconds: int = 300
    proxy_url: str | None = None
    request_timeout_seconds: float = 600.0
    max_retries: int = 4

    @classmethod
    def from_env(cls) -> "AnalysisSettings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            transcription_model=os.getenv(
                "OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-transcribe-diarize"
            ),
            extraction_model=os.getenv("OPENAI_EXTRACTION_MODEL", "gpt-5.6-terra"),
            confidence_threshold=float(
                os.getenv("ANALYSIS_CONFIDENCE_THRESHOLD", "0.75")
            ),
            audio_chunk_seconds=max(
                30, int(os.getenv("OPENAI_AUDIO_CHUNK_SECONDS", "300"))
            ),
            proxy_url=os.getenv("OPENAI_PROXY_URL") or None,
            request_timeout_seconds=max(
                30.0, float(os.getenv("OPENAI_REQUEST_TIMEOUT_SECONDS", "600"))
            ),
            max_retries=max(0, int(os.getenv("OPENAI_MAX_RETRIES", "4"))),
        )
