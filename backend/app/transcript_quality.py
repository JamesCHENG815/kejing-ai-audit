"""Filter transcription hallucinations before they reach the evidence chain.

``gpt-4o-transcribe`` invents text when fed silence or background music. Those
invented segments are dangerous here because every field value must be backed by
a verbatim quote: a hallucinated line can look like valid evidence.

This module is deliberately dependency-free (standard library only) so it can be
exercised with ``python -m app.transcript_quality``.

Filtering is intentionally conservative. Dropping a real segment costs more than
keeping a fake one, because the extraction step degrades gracefully (a spurious
line simply fails to match a field) while a missing line loses information
irrecoverably.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Protocol, TypeVar


logger = logging.getLogger(__name__)

# Same value as app.database.BACKEND_DIR; duplicated to stay import-free.
PHRASES_FILE = Path(__file__).resolve().parents[1] / "prompts" / "hallucination_phrases.txt"

# A segment shorter than this that still carries a long sentence is a strong
# hallucination signal: real speech cannot pack 20+ characters into 0.3s.
MIN_REAL_DURATION_SECONDS = 0.3
LONG_TEXT_CHARS = 20

# An identical 12+ character line repeated more than twice is never a real
# conversation. Short repeats ("好的", "对") are legitimate, so they are exempt.
DUPLICATE_MIN_CHARS = 12
MAX_DUPLICATE_KEPT = 2

def _normalize(text: str) -> str:
    """Strip spaces and punctuation, fold case; keep CJK, letters and digits."""
    return re.sub(
        r"[\W_]+", "", unicodedata.normalize("NFKC", text or "").lower()
    )


_DEFAULT_PHRASES_RAW: tuple[str, ...] = (
    "谢谢观看",
    "感谢观看",
    "请点赞订阅",
    "点赞订阅",
    "订阅频道",
    "请关注我们",
    "字幕由",
    "字幕提供",
    "本字幕由",
    "thanks for watching",
    "subtitles by",
    "amara.org",
)

# Stored pre-normalised so it is directly comparable with load_phrases().
DEFAULT_PHRASES: tuple[str, ...] = tuple(
    _normalize(item) for item in _DEFAULT_PHRASES_RAW
)

_CACHE: tuple[float, tuple[str, ...]] | None = None


class SegmentLike(Protocol):
    text: str
    start_seconds: float
    end_seconds: float


SegmentT = TypeVar("SegmentT", bound=SegmentLike)


def load_phrases() -> tuple[str, ...]:
    """Read the phrase list, cached by file modification time."""
    global _CACHE

    try:
        mtime = PHRASES_FILE.stat().st_mtime
    except OSError:
        return DEFAULT_PHRASES
    if _CACHE is not None and _CACHE[0] == mtime:
        return _CACHE[1]

    try:
        raw = PHRASES_FILE.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("无法读取幻觉词表 %s：%s", PHRASES_FILE, exc)
        return DEFAULT_PHRASES

    phrases: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        normalized = _normalize(stripped)
        if normalized:
            phrases.append(normalized)

    result = tuple(phrases) or DEFAULT_PHRASES
    _CACHE = (mtime, result)
    return result


def has_speakable_content(text: str) -> bool:
    """True when the text contains at least one CJK character, letter or digit."""
    return bool(re.search(r"[0-9A-Za-z\u3400-\u4dbf\u4e00-\u9fff]", text or ""))


def _matches_phrase(normalized: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in normalized for phrase in phrases)


def is_hallucination_phrase(text: str) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    return _matches_phrase(normalized, load_phrases())


def filter_hallucinated_segments(segments: list[SegmentT]) -> list[SegmentT]:
    """Drop segments that are almost certainly model output, not speech."""
    kept: list[SegmentT] = []
    duplicates: dict[str, int] = {}
    dropped = {"empty": 0, "phrase": 0, "duration": 0, "duplicate": 0}
    # Resolved once per transcript: the loader hits the filesystem for the mtime.
    phrases = load_phrases()

    for segment in segments:
        text = (segment.text or "").strip()
        if not has_speakable_content(text):
            dropped["empty"] += 1
            continue

        normalized = _normalize(text)
        if _matches_phrase(normalized, phrases):
            dropped["phrase"] += 1
            continue

        duration = float(segment.end_seconds) - float(segment.start_seconds)
        if duration < MIN_REAL_DURATION_SECONDS and len(normalized) >= LONG_TEXT_CHARS:
            dropped["duration"] += 1
            continue

        if len(normalized) >= DUPLICATE_MIN_CHARS:
            seen = duplicates.get(normalized, 0) + 1
            duplicates[normalized] = seen
            if seen > MAX_DUPLICATE_KEPT:
                dropped["duplicate"] += 1
                continue

        kept.append(segment)

    removed = sum(dropped.values())
    if removed:
        logger.info(
            "已丢弃疑似幻觉转写片段 %s 条（空文本 %s / 命中词表 %s / 时长异常 %s / 重复长句 %s）",
            removed,
            dropped["empty"],
            dropped["phrase"],
            dropped["duration"],
            dropped["duplicate"],
        )
    return kept


def _main() -> int:
    """Self-check: ``python -m app.transcript_quality``."""

    class _S:
        __slots__ = ("text", "start_seconds", "end_seconds")

        def __init__(self, text: str, start: float, end: float) -> None:
            self.text = text
            self.start_seconds = start
            self.end_seconds = end

    samples = [
        (_S("去年马爹利卖了二十万。", 0, 3), True, "正常对话"),
        (_S("谢谢观看。", 4, 6), False, "命中词表"),
        (_S("请 点赞，订阅！", 6, 7), False, "标点/空格不影响命中"),
        (_S("？？？", 8, 9), False, "无实义字符"),
        (_S("这句很长的话出现在不到零点三秒的时间里肯定是模型编的", 9, 9.1), False, "时长异常"),
        (_S("好的", 10, 11), True, "短重复词应保留"),
        (_S("轩尼诗今年到上个月做了十二万。", 13, 16), True, "正常对话"),
    ]
    failed = 0
    for segment, expected, label in samples:
        kept = filter_hallucinated_segments([segment])
        actual = len(kept) == 1
        flag = "OK  " if actual == expected else "FAIL"
        if actual != expected:
            failed += 1
        print(f"[{flag}] {label}：保留={actual} 期望={expected}")

    repeated = [
        _S("轩尼诗今年到上个月做了十二万。", 13, 16),
        _S("轩尼诗今年到上个月做了十二万。", 17, 20),
        _S("轩尼诗今年到上个月做了十二万。", 21, 24),
        _S("好的", 25, 26),
        _S("好的", 27, 28),
        _S("好的", 29, 30),
    ]
    kept_group = len(filter_hallucinated_segments(repeated))
    group_ok = kept_group == 5
    print(f"[{'OK  ' if group_ok else 'FAIL'}] 重复长句只保留 2 次、短重复全保留：保留 {kept_group} 条（期望 5）")
    if not group_ok:
        failed += 1

    print(f"\n词表条目：{len(load_phrases())} 条（{PHRASES_FILE}）")
    print("结果：" + ("全部通过" if failed == 0 else f"{failed} 项失败"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_main())
