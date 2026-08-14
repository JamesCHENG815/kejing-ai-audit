from contextlib import contextmanager
from types import SimpleNamespace

from app.services.analysis_service import (
    MANDARIN_TRANSCRIPTION_LANGUAGE,
    OpenAIAnalysisProvider,
    TranscriptReference,
    _ModelExtractedField,
    _ModelExtractionResponse,
    _audio_chunk_ranges,
)
from app.services import analysis_service
from app.settings import AnalysisSettings


def provider_with_client(client):
    provider = OpenAIAnalysisProvider.__new__(OpenAIAnalysisProvider)
    provider.settings = AnalysisSettings(
        openai_api_key="test-key",
        transcription_model="gpt-4o-transcribe-diarize",
        extraction_model="gpt-4o-mini",
        confidence_threshold=0.75,
    )
    provider.client = client
    return provider


def test_openai_transcription_adapter_requests_diarized_segments(tmp_path):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            segments=[
                SimpleNamespace(
                    start=1.2,
                    end=3.4,
                    speaker="speaker_0",
                    text="去年马爹利二十万",
                )
            ]
        )

    client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(create=create)
        )
    )
    audio_path = tmp_path / "real.m4a"
    audio_path.write_bytes(b"audio")

    segments = provider_with_client(client).transcribe(audio_path)

    assert len(segments) == 1
    assert segments[0].speaker == "speaker_0"
    assert calls[0]["model"] == "gpt-4o-transcribe-diarize"
    assert calls[0]["response_format"] == "diarized_json"
    assert calls[0]["chunking_strategy"] == "auto"
    assert calls[0]["language"] == MANDARIN_TRANSCRIPTION_LANGUAGE == "zh"


def test_openai_transcription_chunks_long_audio_and_restores_timeline(
    tmp_path, monkeypatch
):
    audio_path = tmp_path / "long.m4a"
    audio_path.write_bytes(b"long-audio")
    chunk_paths = [tmp_path / "chunk-0.m4a", tmp_path / "chunk-1.m4a"]
    for path in chunk_paths:
        path.write_bytes(b"chunk")

    @contextmanager
    def fake_chunks(_path, _duration, _chunk_seconds):
        yield [(chunk_paths[0], 0.0), (chunk_paths[1], 300.0)]

    monkeypatch.setattr(analysis_service, "_probe_audio_duration", lambda _path: 600)
    monkeypatch.setattr(analysis_service, "_chunk_audio", fake_chunks)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            segments=[
                SimpleNamespace(
                    start=1.0,
                    end=2.0,
                    speaker="speaker_0",
                    text="有效片段",
                )
            ]
        )

    client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
    )

    segments = provider_with_client(client).transcribe(audio_path)

    assert len(calls) == 2
    assert all(
        call["language"] == MANDARIN_TRANSCRIPTION_LANGUAGE
        for call in calls
    )
    assert [(item.start_seconds, item.end_seconds) for item in segments] == [
        (1.0, 2.0),
        (301.0, 302.0),
    ]


def test_audio_chunks_merge_tiny_final_tail():
    assert _audio_chunk_ranges(901.4, 300) == [
        (0.0, 300.0),
        (300.0, 300.0),
        (600.0, 301.4),
    ]


def test_audio_chunks_keep_normal_final_chunk():
    assert _audio_chunk_ranges(920.0, 300) == [
        (0.0, 300.0),
        (300.0, 300.0),
        (600.0, 300.0),
        (900.0, 20.0),
    ]


def test_openai_extraction_adapter_reads_structured_output():
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=_ModelExtractionResponse(
                fields=[
                    _ModelExtractedField(
                        field_name="马爹利上一个自然年零售金额(万元)(2025年)",
                        value="20",
                        unit="万元",
                        confidence=0.95,
                        recording_id=7,
                        segment_index=0,
                    )
                ]
            )
        )

    client = SimpleNamespace(
        responses=SimpleNamespace(parse=parse)
    )
    targets = [("马爹利上一个自然年零售金额(万元)(2025年)", "万元")]
    transcript = [
        TranscriptReference(7, 0, 1.2, 3.4, "speaker_0", "去年马爹利二十万")
    ]

    fields = provider_with_client(client).extract_fields(targets, transcript)

    assert len(fields) == 1
    assert fields[0].value == "20"
    assert calls[0]["model"] == "gpt-4o-mini"
    assert calls[0]["text_format"] is _ModelExtractionResponse
