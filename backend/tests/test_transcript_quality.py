from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

from app import transcript_quality
from app.transcript_quality import (
    filter_hallucinated_segments,
    has_speakable_content,
    is_hallucination_phrase,
)


@dataclass(frozen=True)
class Segment:
    """Stand-in for TranscribedSegmentData.

    The filter is duck-typed on purpose, so the real model object does not need
    to be imported here (which would drag in the web stack).
    """

    text: str
    start_seconds: float
    end_seconds: float


def test_real_sentence_is_kept():
    segment = Segment("去年马爹利大概二十万。", 0.0, 3.0)
    assert filter_hallucinated_segments([segment]) == [segment]


@pytest.mark.parametrize(
    "text",
    [
        "谢谢观看。",
        "感谢观看",
        "请点赞订阅",
        "点赞 订阅 转发",
        "字幕由 ABC 字幕组提供",
        "Thanks for watching!",
    ],
)
def test_known_hallucination_phrases_are_dropped(text):
    assert is_hallucination_phrase(text)
    assert filter_hallucinated_segments([Segment(text, 0.0, 2.0)]) == []


def test_punctuation_and_spacing_do_not_defeat_the_phrase_list():
    assert is_hallucination_phrase("谢 谢，观 看！")


def test_text_without_letters_or_digits_is_dropped():
    assert not has_speakable_content("？？？")
    assert filter_hallucinated_segments([Segment("？？？", 0.0, 1.0)]) == []


def test_long_text_in_an_impossibly_short_window_is_dropped():
    segment = Segment("这一整句话不可能在零点二秒里说完肯定是模型凭空生成的", 5.0, 5.2)
    assert filter_hallucinated_segments([segment]) == []


def test_short_interjections_are_not_treated_as_duplicates():
    segments = [Segment("好的", float(i), float(i) + 1.0) for i in range(5)]
    assert filter_hallucinated_segments(segments) == segments


def test_long_identical_line_is_kept_at_most_twice():
    segments = [
        Segment("轩尼诗今年截止到上个月做了十二万。", float(i * 3), float(i * 3 + 3))
        for i in range(4)
    ]
    kept = filter_hallucinated_segments(segments)
    assert len(kept) == transcript_quality.MAX_DUPLICATE_KEPT


def test_mixed_recording_keeps_only_real_speech():
    segments = [
        Segment("去年马爹利卖了二十万。", 0.0, 4.0),
        Segment("谢谢观看。", 4.0, 5.0),
        Segment("卖得最好的是马爹利蓝带。", 5.0, 9.0),
        Segment("？？", 9.0, 9.5),
    ]
    kept = filter_hallucinated_segments(segments)
    assert [item.text for item in kept] == [
        "去年马爹利卖了二十万。",
        "卖得最好的是马爹利蓝带。",
    ]


def test_missing_phrase_file_falls_back_to_builtin_list(tmp_path, monkeypatch):
    monkeypatch.setattr(transcript_quality, "PHRASES_FILE", tmp_path / "missing.txt")
    monkeypatch.setattr(transcript_quality, "_CACHE", None)

    assert is_hallucination_phrase("谢谢观看")
    assert transcript_quality.load_phrases() == transcript_quality.DEFAULT_PHRASES


def test_phrase_file_is_reread_after_edit(tmp_path, monkeypatch):
    phrase_file = tmp_path / "phrases.txt"
    phrase_file.write_text("# 注释\n本店独家话术\n", encoding="utf-8")
    monkeypatch.setattr(transcript_quality, "PHRASES_FILE", phrase_file)
    monkeypatch.setattr(transcript_quality, "_CACHE", None)

    assert is_hallucination_phrase("本店独家话术")

    # A later write with a different timestamp must invalidate the cache without
    # any explicit reset - that is what makes hot-reloading the word list work.
    phrase_file.write_text("另一句话术\n", encoding="utf-8")
    os.utime(phrase_file, (1_000_000.0, 1_000_000.0))

    assert is_hallucination_phrase("另一句话术")
    assert not is_hallucination_phrase("本店独家话术")
