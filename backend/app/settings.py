from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from app.audio_preprocess import DEFAULT_SPEECH_FILTERS
from app.database import BACKEND_DIR


load_dotenv(BACKEND_DIR / ".env")


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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
    normalize_audio: bool = True
    audio_filters: str = DEFAULT_SPEECH_FILTERS

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
            # Pre-processing is the cheapest accuracy win for pocket recordings:
            # it lifts quiet audio to a consistent level. Set to false to keep
            # the previous "upload the original file" behaviour.
            normalize_audio=_env_flag("OPENAI_AUDIO_NORMALIZE", True),
            audio_filters=os.getenv(
                "OPENAI_AUDIO_FILTERS", DEFAULT_SPEECH_FILTERS
            ).strip(),
        )
