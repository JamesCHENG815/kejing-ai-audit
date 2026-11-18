"""Audio preparation before transcription.

Field recordings from store visits have three recurring problems: the phone sits
in a pocket (low level, far field), there is background music, and the original
container is often 44.1 kHz stereo AAC while the transcription model only cares
about 16 kHz mono speech.

``loudnorm`` is the single highest-value step here - it brings every recording to
a consistent loudness so quiet ones stop being mis-recognised.

Deliberately no denoising: aggressive noise reduction eats consonants and
measurably hurts ASR, especially over music. If it is ever enabled it must be
A/B tested, not switched on by default.

Standard library only (shells out to ffmpeg), so it can be exercised with
``python -m app.audio_preprocess <录音文件>``.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path


logger = logging.getLogger(__name__)

# EBU R128, -16 LUFS: the usual target for speech. highpass=80 removes the
# handling rumble that phones pick up without touching speech formants.
DEFAULT_SPEECH_FILTERS = "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11"

# Used only when the lossless file would exceed the API upload limit.
FALLBACK_BITRATE = "48k"
FFMPEG_TIMEOUT_SECONDS = 900


class AudioPreprocessError(RuntimeError):
    """ffmpeg missing, unreadable input, or a failed conversion."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            check=False,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AudioPreprocessError(f"ffmpeg 执行失败：{exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        raise AudioPreprocessError(
            "ffmpeg 转换失败：" + (detail[-1] if detail else "未返回错误信息")
        )
    return completed


def normalize_audio(
    source: Path,
    destination: Path,
    *,
    filters: str = DEFAULT_SPEECH_FILTERS,
) -> Path:
    """Convert to 16 kHz mono FLAC with loudness normalisation.

    FLAC rather than AAC: it avoids a second lossy encode of already-lossy input
    and a 16 kHz mono stream stays small enough that most recordings fit the
    25 MB upload limit without chunking.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AudioPreprocessError("未找到 ffmpeg，无法进行音频规范化")

    destination.parent.mkdir(parents=True, exist_ok=True)
    args = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        # Pin the first audio stream explicitly so a cover image or video track
        # in the container can never be mistaken for the source.
        "-map",
        "0:a:0",
        "-ac",
        "1",
        "-ar",
        "16000",
    ]
    if filters.strip():
        args += ["-af", filters.strip()]
    args += ["-c:a", "flac", str(destination)]

    _run(args)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise AudioPreprocessError("ffmpeg 未生成有效的规范化音频")
    return destination


def compress_for_transcription(
    source: Path, destination: Path, *, bitrate: str = FALLBACK_BITRATE
) -> Path:
    """Re-encode an already normalised file to fit the upload limit.

    Only used when the lossless file exceeds 25 MB (~65 minutes of speech).
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AudioPreprocessError("未找到 ffmpeg，无法压缩音频")

    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "aac",
            "-b:a",
            bitrate,
            str(destination),
        ]
    )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise AudioPreprocessError("ffmpeg 未生成有效的压缩音频")
    return destination


def _main(argv: list[str]) -> int:
    """Self-check: ``python -m app.audio_preprocess <录音文件> [输出目录]``."""
    if not ffmpeg_available():
        print("[FAIL] 未找到 ffmpeg，请先安装并加入 PATH")
        return 1
    print(f"[OK] ffmpeg：{shutil.which('ffmpeg')}")
    print(f"[OK] 默认滤镜：{DEFAULT_SPEECH_FILTERS}")

    if len(argv) < 2:
        print("\n用法：python -m app.audio_preprocess <录音文件> [输出目录]")
        return 0

    source = Path(argv[1]).expanduser().resolve()
    if not source.is_file():
        print(f"[FAIL] 文件不存在：{source}")
        return 1
    out_dir = Path(argv[2]).expanduser().resolve() if len(argv) > 2 else source.parent
    target = out_dir / (source.stem + ".normalized.flac")

    before = source.stat().st_size
    normalize_audio(source, target)
    after = target.stat().st_size
    print(f"\n[OK] 输出：{target}")
    print(f"     原始 {before / 1e6:.2f} MB → 规范化 {after / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
