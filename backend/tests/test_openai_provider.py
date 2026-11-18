from contextlib import contextmanager
from types import SimpleNamespace

from app.audio_preprocess import AudioPreprocessError
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
from app.transcription_prompt import build_task_context, build_transcription_prompt


def provider_with_client(client, *, normalize_audio: bool = False):
    provider = OpenAIAnalysisProvider.__new__(OpenAIAnalysisProvider)
    provider.settings = AnalysisSettings(
        openai_api_key="test-key",
        transcription_model="gpt-4o-transcribe-diarize",
        extraction_model="gpt-5.6-terra",
        confidence_threshold=0.75,
        # Pre-processing shells out to ffmpeg. These are adapter tests, so it is
        # off by default here; the pre-processing matrix is covered by the
        # _prepared_audio tests below.
        normalize_audio=normalize_audio,
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
    # The domain prompt is always sent, otherwise the model guesses at brand
    # names and one wrong character breaks the downstream field match.
    assert calls[0]["prompt"] == build_transcription_prompt("")


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
    monkeypatch.setattr(
        analysis_service, "_audio_file_fits_api_limit", lambda _path: False
    )
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


def test_transcription_keeps_long_audio_whole_when_file_fits_api_limit(
    tmp_path, monkeypatch
):
    audio_path = tmp_path / "long-but-small.m4a"
    audio_path.write_bytes(b"audio")
    provider = provider_with_client(SimpleNamespace())
    expected = [
        analysis_service.TranscribedSegmentData(0.0, 600.0, "A", "普通话录音")
    ]
    calls = []

    def transcribe_single(path, prompt=""):
        calls.append(path)
        return expected

    monkeypatch.setattr(provider, "_transcribe_single", transcribe_single)
    monkeypatch.setattr(
        analysis_service, "_probe_audio_duration", lambda _path: 600
    )

    assert provider.transcribe(audio_path) == expected
    assert calls == [audio_path]


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
    assert calls[0]["model"] == "gpt-5.6-terra"
    assert calls[0]["text_format"] is _ModelExtractionResponse


def test_transcription_prompt_carries_store_and_salesperson(tmp_path):
    audio_path = tmp_path / "visit.m4a"
    audio_path.write_bytes(b"audio")
    captured = []

    def create(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(segments=[])

    client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
    )
    provider_with_client(client).transcribe(
        audio_path, hotwords=build_task_context("建设路烟酒行", "张三")
    )

    prompt = captured[0]["prompt"]
    assert "建设路烟酒行" in prompt
    assert "张三" in prompt
    assert prompt.startswith(build_transcription_prompt(""))


def test_prepared_audio_uses_normalised_copy(tmp_path, monkeypatch):
    source = tmp_path / "src.m4a"
    source.write_bytes(b"x")
    seen = {}

    def fake_normalize(_src, dst, *, filters=""):
        seen["filters"] = filters
        dst.write_bytes(b"f" * 32)
        return dst

    monkeypatch.setattr(analysis_service, "normalize_audio", fake_normalize)
    provider = provider_with_client(SimpleNamespace(), normalize_audio=True)

    with provider._prepared_audio(source) as prepared:
        assert prepared != source
        assert prepared.suffix == ".flac"
    assert seen["filters"] == provider.settings.audio_filters


def test_prepared_audio_falls_back_to_original_when_ffmpeg_fails(
    tmp_path, monkeypatch
):
    source = tmp_path / "src.m4a"
    source.write_bytes(b"x")

    def boom(_src, _dst, *, filters=""):
        raise AudioPreprocessError("未找到 ffmpeg")

    monkeypatch.setattr(analysis_service, "normalize_audio", boom)
    provider = provider_with_client(SimpleNamespace(), normalize_audio=True)

    with provider._prepared_audio(source) as prepared:
        assert prepared == source


def test_prepared_audio_compresses_when_lossless_exceeds_limit(
    tmp_path, monkeypatch
):
    source = tmp_path / "src.m4a"
    source.write_bytes(b"x")

    def fake_normalize(_src, dst, *, filters=""):
        dst.write_bytes(b"f" * 64)
        return dst

    def fake_compress(_src, dst, *, bitrate="48k"):
        dst.write_bytes(b"c" * 16)
        return dst

    monkeypatch.setattr(analysis_service, "normalize_audio", fake_normalize)
    monkeypatch.setattr(
        analysis_service, "compress_for_transcription", fake_compress
    )
    monkeypatch.setattr(
        analysis_service,
        "_audio_file_fits_api_limit",
        lambda path: path.suffix == ".m4a",
    )
    provider = provider_with_client(SimpleNamespace(), normalize_audio=True)

    with provider._prepared_audio(source) as prepared:
        assert prepared.suffix == ".m4a"


def test_prepared_audio_is_skipped_when_normalisation_is_disabled(tmp_path):
    source = tmp_path / "src.m4a"
    source.write_bytes(b"x")
    provider = provider_with_client(SimpleNamespace())

    with provider._prepared_audio(source) as prepared:
        assert prepared == source
