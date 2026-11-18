from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from app.audio_preprocess import (
    AudioPreprocessError,
    compress_for_transcription,
    ffmpeg_available,
    normalize_audio,
)


pytestmark = pytest.mark.skipif(
    not ffmpeg_available(), reason="需要 ffmpeg 才能测试音频预处理"
)


def _make_recording(path, *, seconds: int = 3) -> None:
    """A quiet 44.1 kHz stereo AAC file, like a phone pocket recording."""
    subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-af",
            "volume=0.04",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(path),
        ],
        check=True,
    )


def _probe(path) -> dict:
    completed = subprocess.run(
        [
            shutil.which("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,sample_rate,channels:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def _mean_volume(path) -> float:
    completed = subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in completed.stderr.splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].split("dB")[0])
    raise AssertionError("volumedetect 未返回 mean_volume")


def test_normalize_produces_16k_mono_flac(tmp_path):
    source = tmp_path / "visit.m4a"
    _make_recording(source)

    target = normalize_audio(source, tmp_path / "out" / "audio.flac")

    streams = _probe(target)["streams"]
    assert len(streams) == 1
    assert streams[0]["codec_name"] == "flac"
    assert streams[0]["sample_rate"] == "16000"
    assert streams[0]["channels"] == 1


def test_normalize_preserves_duration(tmp_path):
    source = tmp_path / "visit.m4a"
    _make_recording(source, seconds=4)

    target = normalize_audio(source, tmp_path / "audio.flac")

    original = float(_probe(source)["format"]["duration"])
    converted = float(_probe(target)["format"]["duration"])
    assert abs(original - converted) < 0.2


def test_normalize_raises_the_level_of_a_quiet_recording(tmp_path):
    source = tmp_path / "visit.m4a"
    _make_recording(source)
    before = _mean_volume(source)

    target = normalize_audio(source, tmp_path / "audio.flac")

    assert _mean_volume(target) > before + 10


def test_normalize_drops_embedded_cover_art(tmp_path):
    """Phones store cover art as a video stream; it must not reach the model."""
    audio = tmp_path / "audio.m4a"
    _make_recording(audio)
    cover = tmp_path / "cover.jpg"
    subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64",
            "-frames:v",
            "1",
            str(cover),
        ],
        check=True,
    )
    with_cover = tmp_path / "with-cover.m4a"
    subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(audio),
            "-i",
            str(cover),
            "-map",
            "0:a",
            "-map",
            "1:v",
            "-c",
            "copy",
            "-disposition:v",
            "attached_pic",
            str(with_cover),
        ],
        check=True,
    )
    assert any(item["codec_type"] == "video" for item in _probe(with_cover)["streams"])

    target = normalize_audio(with_cover, tmp_path / "audio.flac")

    assert [item["codec_type"] for item in _probe(target)["streams"]] == ["audio"]


def test_normalize_raises_on_a_non_audio_input(tmp_path):
    broken = tmp_path / "broken.m4a"
    broken.write_bytes(b"not audio")

    with pytest.raises(AudioPreprocessError):
        normalize_audio(broken, tmp_path / "audio.flac")


def test_missing_ffmpeg_is_reported_not_silently_ignored(tmp_path, monkeypatch):
    source = tmp_path / "visit.m4a"
    source.write_bytes(b"x")
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    with pytest.raises(AudioPreprocessError):
        normalize_audio(source, tmp_path / "audio.flac")


def test_compress_shrinks_the_lossless_copy(tmp_path):
    source = tmp_path / "visit.m4a"
    _make_recording(source, seconds=5)
    lossless = normalize_audio(source, tmp_path / "audio.flac")

    compressed = compress_for_transcription(lossless, tmp_path / "audio.m4a")

    assert compressed.stat().st_size < lossless.stat().st_size
    streams = _probe(compressed)["streams"]
    assert streams[0]["codec_name"] == "aac"
    assert streams[0]["sample_rate"] == "16000"
    assert streams[0]["channels"] == 1
