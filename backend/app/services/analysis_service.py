from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.database import BACKEND_DIR, SessionLocal
from app.field_rules import (
    EvidenceValue,
    determine_field_status,
    evidence_context_is_sufficient,
    evidence_supports_value,
    infer_unit,
    is_auditable_field,
    required_audit_field_names,
)
from app.models import (
    AIFieldResult,
    AuditTask,
    ImportBatch,
    Recording,
    TaskRecording,
    TranscriptSegment,
)
from app.settings import AnalysisSettings


logger = logging.getLogger(__name__)
MIN_AUDIO_CHUNK_SECONDS = 10.0
# OpenAI's transcription API accepts ISO-639-1 language codes. Fix every
# recording (including generated chunks) to Chinese instead of auto-detection;
# this project's Chinese recordings are all spoken in Mandarin.
MANDARIN_TRANSCRIPTION_LANGUAGE = "zh"
OCEAN_SPIRIT_BRANDS = ("马爹利", "轩尼诗", "人头马")
OCEAN_SPLIT_SCALE = Decimal("0.01")


@dataclass(frozen=True)
class TranscribedSegmentData:
    start_seconds: float
    end_seconds: float
    speaker: str | None
    text: str


@dataclass(frozen=True)
class TranscriptReference:
    recording_id: int
    segment_index: int
    start_seconds: float
    end_seconds: float
    speaker: str | None
    text: str
    context: str = ""


@dataclass(frozen=True)
class ExtractedFieldData:
    field_name: str
    value: str
    unit: str | None
    confidence: float
    recording_id: int
    segment_index: int


class AnalysisProvider(Protocol):
    def transcribe(self, audio_path: Path) -> list[TranscribedSegmentData]: ...

    def extract_fields(
        self,
        targets: list[tuple[str, str | None]],
        transcript: list[TranscriptReference],
    ) -> list[ExtractedFieldData]: ...


class AnalysisConfigurationError(RuntimeError):
    pass


class AnalysisProviderError(RuntimeError):
    pass


class _ModelExtractedField(BaseModel):
    field_name: str
    value: str
    unit: str | None
    confidence: float = Field(ge=0, le=1)
    recording_id: int
    segment_index: int = Field(ge=0)


class _ModelExtractionResponse(BaseModel):
    fields: list[_ModelExtractedField]


def _probe_audio_duration(audio_path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    try:
        return float(completed.stdout.strip()) if completed.returncode == 0 else None
    except ValueError:
        return None


@contextmanager
def _chunk_audio(audio_path: Path, duration: float, chunk_seconds: int):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AnalysisConfigurationError(
            "长录音分片需要 ffmpeg，请安装 ffmpeg 或增大 OPENAI_AUDIO_CHUNK_SECONDS"
        )
    with tempfile.TemporaryDirectory(prefix="kejing-audio-") as directory:
        chunks: list[tuple[Path, float]] = []
        for offset, chunk_duration in _audio_chunk_ranges(duration, chunk_seconds):
            output_path = Path(directory) / f"chunk-{len(chunks):04d}.m4a"
            completed = subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    str(offset),
                    "-t",
                    str(chunk_duration),
                    "-i",
                    str(audio_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "64k",
                    str(output_path),
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            if completed.returncode != 0 or not output_path.is_file():
                raise AnalysisProviderError(
                    f"录音分片失败：{completed.stderr.strip() or 'ffmpeg 未生成文件'}"
                )
            chunks.append((output_path, offset))
        yield chunks


def _audio_chunk_ranges(
    duration: float, chunk_seconds: int
) -> list[tuple[float, float]]:
    """Split audio without leaving a tiny, failure-prone final request."""
    ranges: list[tuple[float, float]] = []
    offset = 0.0
    while offset < duration:
        remaining = duration - offset
        chunk_duration = (
            remaining
            if remaining <= chunk_seconds + MIN_AUDIO_CHUNK_SECONDS
            else float(chunk_seconds)
        )
        ranges.append((offset, chunk_duration))
        offset += chunk_duration
    return ranges


class OpenAIAnalysisProvider:
    def __init__(self, settings: AnalysisSettings | None = None):
        self.settings = settings or AnalysisSettings.from_env()
        if not self.settings.openai_api_key:
            raise AnalysisConfigurationError(
                "缺少 OPENAI_API_KEY，无法执行真实录音转写和字段提取"
            )
        try:
            from openai import DefaultHttpxClient, OpenAI
        except ImportError as exc:
            raise AnalysisConfigurationError(
                "缺少 openai Python SDK，请安装 requirements.txt"
            ) from exc
        http_client = DefaultHttpxClient(
            proxy=self.settings.proxy_url,
            timeout=self.settings.request_timeout_seconds,
        )
        self.client = OpenAI(
            api_key=self.settings.openai_api_key,
            http_client=http_client,
            max_retries=self.settings.max_retries,
        )

    def _transcribe_single(self, audio_path: Path) -> list[TranscribedSegmentData]:
        try:
            with audio_path.open("rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model=self.settings.transcription_model,
                    file=audio_file,
                    response_format="diarized_json",
                    chunking_strategy="auto",
                    language=MANDARIN_TRANSCRIPTION_LANGUAGE,
                )
        except Exception as exc:
            raise AnalysisProviderError(f"语音转写服务调用失败：{exc}") from exc

        segments: list[TranscribedSegmentData] = []
        for segment in transcript.segments or []:
            text = str(segment.text or "").strip()
            start = float(segment.start)
            end = float(segment.end)
            if not text or start < 0 or end < start:
                continue
            segments.append(
                TranscribedSegmentData(
                    start_seconds=start,
                    end_seconds=end,
                    speaker=str(segment.speaker) if segment.speaker else None,
                    text=text,
                )
            )
        return segments

    def transcribe(self, audio_path: Path) -> list[TranscribedSegmentData]:
        if not audio_path.is_file():
            raise AnalysisProviderError(f"录音文件不存在：{audio_path}")
        duration = _probe_audio_duration(audio_path)
        if duration is None or duration <= self.settings.audio_chunk_seconds:
            return self._transcribe_single(audio_path)

        segments: list[TranscribedSegmentData] = []
        with _chunk_audio(
            audio_path, duration, self.settings.audio_chunk_seconds
        ) as chunks:
            for chunk_path, offset in chunks:
                for item in self._transcribe_single(chunk_path):
                    segments.append(
                        TranscribedSegmentData(
                            start_seconds=item.start_seconds + offset,
                            end_seconds=item.end_seconds + offset,
                            speaker=item.speaker,
                            text=item.text,
                        )
                    )
        return segments

    def extract_fields(
        self,
        targets: list[tuple[str, str | None]],
        transcript: list[TranscriptReference],
    ) -> list[ExtractedFieldData]:
        if not targets or not transcript:
            return []
        target_payload = [
            {"field_name": field_name, "expected_unit": unit}
            for field_name, unit in targets
        ]
        transcript_payload = [
            {
                "recording_id": item.recording_id,
                "segment_index": item.segment_index,
                "speaker": item.speaker,
                "start_seconds": item.start_seconds,
                "end_seconds": item.end_seconds,
                "text": item.text,
                "context": item.context,
            }
            for item in transcript
        ]
        system_prompt = """你是门店拜访录音的数据抽取器。只能输出录音原文明确支持的字段，禁止猜测、补全、换算未说出的值或使用 Excel 值推断。
规则：
1. field_name 必须逐字来自目标字段；没有明确提及的字段不要输出。“三大洋合计……”和“……占三大洋……比例(%)”是拆分用的中间字段，仅在录音明确说出合计或对应品牌占比时输出。
2. recording_id 和 segment_index 必须引用给定转写中的一个片段，该片段 text 必须直接包含 value；context 只用于判断品牌、年份和问题范围，不能作为直接证据。
3. 金额按目标 expected_unit 输出；万元字段只输出数值（例如录音说“二十万”，value 输出“20”，unit 输出“万元”）。
4. 畅销产品按录音明确列举的单品顺序填入畅销产品1、2……；“白酒、洋酒、威士忌”等品类不是单品。进货价和瓶数只有能与该单品明确关联时才输出。
5. 销售额必须同时确定品牌和目标时间范围。“今年上半年”不能映射到“今年截止到上个月”；“去年全年”才可映射上一个自然年。回答出现自我纠正、多个互相冲突数字或品牌不明确时不要输出。
6. 问句、猜测或业务员给出的候选数字不能作为门店回答；只有受访者明确确认的陈述才输出。
7. confidence 表示该片段直接支持该字段的可信度，范围 0 到 1。证据含糊、指代不清或无法区分时间范围时不要输出。
8. 不处理任何照片或图片字段。"""
        try:
            response = self.client.responses.parse(
                model=self.settings.extraction_model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "target_fields": target_payload,
                                "transcript_segments": transcript_payload,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                text_format=_ModelExtractionResponse,
            )
        except Exception as exc:
            raise AnalysisProviderError(f"AI 字段提取服务调用失败：{exc}") from exc
        parsed = response.output_parsed
        if parsed is None:
            raise AnalysisProviderError("AI 字段提取未返回结构化结果")
        return [ExtractedFieldData(**item.model_dump()) for item in parsed.fields]


@dataclass(frozen=True)
class AnalysisResult:
    task_id: int
    status: str
    recording_count: int
    transcript_segment_count: int
    ai_result_count: int
    matched: int
    pending: int
    conflict: int
    missing: int


@dataclass(frozen=True)
class _OceanSplitSpec:
    brand: str
    output_field: str
    total_field: str
    share_field: str


def _ocean_split_specs(target_names: list[str]) -> list[_OceanSplitSpec]:
    """Build non-persisted extraction targets used to derive brand amounts."""
    pattern = re.compile(
        r"^(马爹利|轩尼诗|人头马)"
        r"(.*(?:上一个自然年零售金额|今年截止到上个月零售金额).*)$"
    )
    specs: list[_OceanSplitSpec] = []
    for field_name in target_names:
        match = pattern.match(field_name)
        if not match:
            continue
        brand, period = match.groups()
        specs.append(
            _OceanSplitSpec(
                brand=brand,
                output_field=field_name,
                total_field=f"三大洋合计{period}",
                share_field=f"{brand}占三大洋{period}比例(%)",
            )
        )
    return specs


def _decimal_extraction(value: str) -> Decimal | None:
    normalized = unicodedata.normalize("NFKC", value).strip().replace(",", "")
    match = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)\s*%?", normalized)
    if not match:
        return None
    try:
        return Decimal(match.group(1))
    except InvalidOperation:
        return None


def _format_split_amount(value: Decimal) -> str:
    rounded = value.quantize(OCEAN_SPLIT_SCALE, rounding=ROUND_HALF_UP)
    return format(rounded, "f").rstrip("0").rstrip(".") or "0"


def _derive_ocean_brand_amounts(
    specs: list[_OceanSplitSpec],
    extractions: dict[str, tuple[ExtractedFieldData, TranscriptReference]],
) -> set[str]:
    """Fill valid splits and return unresolved output fields needing confirmation."""
    groups: dict[str, list[_OceanSplitSpec]] = {}
    pending_fields: set[str] = set()
    for spec in specs:
        groups.setdefault(spec.total_field, []).append(spec)

    for total_field, group in groups.items():
        if {spec.brand for spec in group} != set(OCEAN_SPIRIT_BRANDS):
            continue
        total_extraction = extractions.get(total_field)
        share_extractions = [extractions.get(spec.share_field) for spec in group]
        missing_output_fields = {
            spec.output_field
            for spec in group
            if spec.output_field not in extractions
        }
        has_split_input = total_extraction is not None or any(
            item is not None for item in share_extractions
        )
        if not missing_output_fields or not has_split_input:
            continue
        if total_extraction is None or any(item is None for item in share_extractions):
            pending_fields.update(missing_output_fields)
            continue
        total_item, total_reference = total_extraction
        if any(
            item is not None
            and item[1].recording_id != total_reference.recording_id
            for item in share_extractions
        ):
            # AIFieldResult can point at only one recording, so do not create a
            # derived value whose calculation evidence cannot be represented.
            pending_fields.update(missing_output_fields)
            continue
        total = _decimal_extraction(total_item.value)
        shares: list[Decimal | None] = []
        for share_extraction in share_extractions:
            assert share_extraction is not None
            shares.append(_decimal_extraction(share_extraction[0].value))
        if (
            total is None
            or total < 0
            or any(share is None or share < 0 for share in shares)
            or sum(share for share in shares if share is not None) != Decimal("100")
        ):
            pending_fields.update(missing_output_fields)
            continue
        for spec, share, share_extraction in zip(
            group, shares, share_extractions, strict=True
        ):
            if spec.output_field in extractions:
                continue
            assert share is not None and share_extraction is not None
            share_item, share_reference = share_extraction
            amount = total * share / Decimal("100")
            calculation_reference = TranscriptReference(
                recording_id=total_reference.recording_id,
                segment_index=share_reference.segment_index,
                start_seconds=min(
                    total_reference.start_seconds, share_reference.start_seconds
                ),
                end_seconds=max(
                    total_reference.end_seconds, share_reference.end_seconds
                ),
                speaker=share_reference.speaker,
                text=f"{total_reference.text} {share_reference.text}",
                context=share_reference.context,
            )
            extractions[spec.output_field] = (
                ExtractedFieldData(
                    field_name=spec.output_field,
                    value=_format_split_amount(amount),
                    unit="万元",
                    confidence=min(total_item.confidence, share_item.confidence),
                    recording_id=share_item.recording_id,
                    segment_index=share_item.segment_index,
                ),
                calculation_reference,
            )
    return pending_fields


def _load_analysis_task(db: Session, task_id: int) -> AuditTask:
    statement = (
        select(AuditTask)
        .where(AuditTask.id == task_id)
        .options(
            selectinload(AuditTask.excel_values),
            selectinload(AuditTask.ai_results),
            selectinload(AuditTask.task_recordings)
            .selectinload(TaskRecording.recording)
            .selectinload(Recording.transcript_segments),
        )
    )
    task = db.scalar(statement)
    if task is None:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    if task.status not in {"pending_analysis", "analysis_failed", "pending"}:
        raise HTTPException(
            status_code=409,
            detail=f"任务状态 {task.status} 不允许执行分析",
        )
    return task


def _recording_path(recording: Recording) -> Path:
    stored_path = Path(recording.file_path)
    return stored_path if stored_path.is_absolute() else BACKEND_DIR / stored_path


def _valid_transcription(
    segments: list[TranscribedSegmentData], recording: Recording
) -> list[TranscribedSegmentData]:
    valid: list[TranscribedSegmentData] = []
    for segment in segments:
        text = segment.text.strip()
        if segment.start_seconds < 0 or segment.end_seconds < segment.start_seconds:
            raise AnalysisProviderError(
                f"录音 {recording.id} 返回了无效转写时间范围"
            )
        if text:
            valid.append(
                TranscribedSegmentData(
                    start_seconds=segment.start_seconds,
                    end_seconds=segment.end_seconds,
                    speaker=segment.speaker,
                    text=text,
                )
            )
    return valid


def _add_transcript_context(
    references: list[TranscriptReference], radius: int = 4
) -> list[TranscriptReference]:
    contextual: list[TranscriptReference] = []
    for index, item in enumerate(references):
        neighbors = references[max(0, index - radius) : index + radius + 1]
        context = "\n".join(
            f"[{neighbor.speaker or '未知'}] {neighbor.text}" for neighbor in neighbors
        )
        contextual.append(
            TranscriptReference(
                recording_id=item.recording_id,
                segment_index=item.segment_index,
                start_seconds=item.start_seconds,
                end_seconds=item.end_seconds,
                speaker=item.speaker,
                text=item.text,
                context=context,
            )
        )
    return contextual


def _persist_transcripts(
    db: Session,
    recordings: list[Recording],
    generated_segments: dict[int, list[TranscribedSegmentData]],
) -> None:
    """Commit paid transcription work before the independent extraction call."""
    try:
        for recording in recordings:
            if recording.id in generated_segments:
                db.execute(
                    delete(TranscriptSegment).where(
                        TranscriptSegment.recording_id == recording.id
                    )
                )
                db.add_all(
                    TranscriptSegment(
                        recording_id=recording.id,
                        start_seconds=item.start_seconds,
                        end_seconds=item.end_seconds,
                        speaker=item.speaker,
                        text=item.text,
                    )
                    for item in generated_segments[recording.id]
                )
                if generated_segments[recording.id]:
                    recording.duration_seconds = max(
                        item.end_seconds for item in generated_segments[recording.id]
                    )
            recording.status = "transcribed"
        db.commit()
    except Exception:
        db.rollback()
        raise


def analyze_task(
    db: Session,
    task_id: int,
    provider: AnalysisProvider,
    *,
    force: bool = False,
    confidence_threshold: float | None = None,
) -> AnalysisResult:
    task = _load_analysis_task(db, task_id)
    settings = AnalysisSettings.from_env()
    threshold = (
        confidence_threshold
        if confidence_threshold is not None
        else settings.confidence_threshold
    )
    recordings = list(
        dict.fromkeys(link.recording for link in task.task_recordings)
    )
    if not recordings:
        raise HTTPException(status_code=409, detail="任务没有关联录音，无法执行分析")
    generated_segments: dict[int, list[TranscribedSegmentData]] = {}
    references: list[TranscriptReference] = []

    for recording in recordings:
        if recording.transcript_segments and not force:
            segment_data = [
                TranscribedSegmentData(
                    start_seconds=item.start_seconds,
                    end_seconds=item.end_seconds,
                    speaker=item.speaker,
                    text=item.text,
                )
                for item in sorted(
                    recording.transcript_segments,
                    key=lambda item: (item.start_seconds, item.id),
                )
            ]
        else:
            segment_data = _valid_transcription(
                provider.transcribe(_recording_path(recording)), recording
            )
            generated_segments[recording.id] = segment_data
        references.extend(
            TranscriptReference(
                recording_id=recording.id,
                segment_index=index,
                start_seconds=item.start_seconds,
                end_seconds=item.end_seconds,
                speaker=item.speaker,
                text=item.text,
            )
            for index, item in enumerate(segment_data)
        )

    # Transcription and extraction are separate paid operations. Persist successful
    # transcripts now so an extraction/model-access failure can be retried without
    # uploading and charging for the audio again.
    _persist_transcripts(db, recordings, generated_segments)
    references = _add_transcript_context(references)

    stored_excel_fields = {
        item.field_name: item
        for item in task.excel_values
        if is_auditable_field(item.field_name)
    }
    target_names = required_audit_field_names(
        task.created_at.year, list(stored_excel_fields)
    )
    excel_fields = {
        field_name: stored_excel_fields.get(field_name)
        for field_name in target_names
    }
    split_specs = _ocean_split_specs(target_names)
    intermediate_units = {
        spec.total_field: "万元" for spec in split_specs
    } | {
        spec.share_field: "%" for spec in split_specs
    }
    targets = [
        (field_name, infer_unit(field_name, item.unit if item else None))
        for field_name, item in excel_fields.items()
    ]
    targets.extend(intermediate_units.items())
    targets = list(dict.fromkeys(targets))
    extracted = provider.extract_fields(targets, references) if references else []
    extraction_target_names = set(excel_fields) | set(intermediate_units)
    reference_map = {
        (item.recording_id, item.segment_index): item for item in references
    }
    best_extraction: dict[str, tuple[ExtractedFieldData, TranscriptReference]] = {}
    for item in extracted:
        reference = reference_map.get((item.recording_id, item.segment_index))
        if (
            item.field_name not in extraction_target_names
            or not item.value.strip()
            or reference is None
            or not 0 <= item.confidence <= 1
            or not evidence_supports_value(
                item.field_name,
                item.value,
                item.unit,
                reference.text,
                reference.context,
            )
        ):
            continue
        current = best_extraction.get(item.field_name)
        validated_item = item
        if not evidence_context_is_sufficient(item.field_name, reference.context):
            validated_item = replace(
                item,
                confidence=min(item.confidence, max(0.0, threshold - 0.01)),
            )
        if current is None or validated_item.confidence > current[0].confidence:
            best_extraction[item.field_name] = (validated_item, reference)

    split_pending_fields = _derive_ocean_brand_amounts(
        split_specs, best_extraction
    )

    try:
        db.execute(delete(AIFieldResult).where(AIFieldResult.task_id == task.id))
        status_counts = {name: 0 for name in ("matched", "pending", "conflict", "missing")}
        for field_name, excel in excel_fields.items():
            extraction = best_extraction.get(field_name)
            if extraction:
                item, reference = extraction
                evidence = EvidenceValue(
                    recording_id=reference.recording_id,
                    start_seconds=reference.start_seconds,
                    end_seconds=reference.end_seconds,
                    text=reference.text,
                )
                value = item.value.strip()
                unit = item.unit or infer_unit(
                    field_name, excel.unit if excel else None
                )
                confidence = item.confidence
            else:
                evidence = None
                value = None
                unit = infer_unit(field_name, excel.unit if excel else None)
                confidence = 0.0
            result_status = determine_field_status(
                field_name,
                excel.field_value if excel else None,
                value,
                confidence,
                evidence,
                excel_unit=excel.unit if excel else None,
                ai_unit=unit,
                confidence_threshold=threshold,
            )
            if extraction is None and field_name in split_pending_fields:
                result_status = "pending"
            status_counts[result_status] += 1
            db.add(
                AIFieldResult(
                    task_id=task.id,
                    field_name=field_name,
                    field_value=value,
                    unit=unit,
                    confidence=confidence,
                    status=result_status,
                    evidence_recording_id=evidence.recording_id if evidence else None,
                    evidence_start_seconds=evidence.start_seconds if evidence else None,
                    evidence_end_seconds=evidence.end_seconds if evidence else None,
                    evidence_text=evidence.text if evidence else None,
                )
            )

        task.status = "pending"
        db.flush()
        remaining = db.scalar(
            select(func.count())
            .select_from(AuditTask)
            .where(
                AuditTask.import_batch_id == task.import_batch_id,
                AuditTask.status.in_(("pending_analysis", "analysis_failed")),
            )
        )
        if remaining == 0:
            batch = db.get(ImportBatch, task.import_batch_id)
            if batch:
                batch.status = "analyzed"
        db.commit()
    except Exception:
        db.rollback()
        raise

    return AnalysisResult(
        task_id=task.id,
        status=task.status,
        recording_count=len(recordings),
        transcript_segment_count=len(references),
        ai_result_count=len(excel_fields),
        **status_counts,
    )


def pending_task_ids(
    db: Session, limit: int, *, batch_id: int | None = None
) -> list[int]:
    statement = select(AuditTask.id).where(
        AuditTask.status.in_(("pending_analysis", "analysis_failed"))
    )
    if batch_id is not None:
        statement = statement.where(AuditTask.import_batch_id == batch_id)
    return list(
        db.scalars(
            statement.order_by(AuditTask.created_at, AuditTask.id).limit(limit)
        )
    )


def analyze_submitted_batch(batch_id: int) -> None:
    """Analyze a submitted batch after the HTTP response has been returned."""
    db = SessionLocal()
    try:
        task_ids = pending_task_ids(db, 10_000, batch_id=batch_id)
        if not task_ids:
            return
        try:
            provider = OpenAIAnalysisProvider()
        except Exception:
            logger.exception("Unable to initialize AI provider for batch %s", batch_id)
            for task_id in task_ids:
                task = db.get(AuditTask, task_id)
                if task:
                    task.status = "analysis_failed"
            batch = db.get(ImportBatch, batch_id)
            if batch:
                batch.status = "analysis_failed"
            db.commit()
            return

        failed = False
        for task_id in task_ids:
            try:
                analyze_task(db, task_id, provider)
            except Exception:
                db.rollback()
                failed = True
                task = db.get(AuditTask, task_id)
                if task:
                    task.status = "analysis_failed"
                    db.commit()
                logger.exception("AI analysis failed for task %s", task_id)
        if failed:
            batch = db.get(ImportBatch, batch_id)
            if batch and batch.status != "analyzed":
                batch.status = "analysis_failed"
                db.commit()
    finally:
        db.close()
