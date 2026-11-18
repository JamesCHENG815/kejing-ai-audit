from __future__ import annotations

import pytest

from app import transcription_prompt
from app.transcription_prompt import (
    DEFAULT_PROMPT_TEXT,
    MAX_PROMPT_CHARS,
    build_task_context,
    build_transcription_prompt,
    load_prompt_text,
    validate_prompt_file,
)


@pytest.fixture
def write_prompt(tmp_path, monkeypatch):
    def _write(text: str):
        path = tmp_path / "transcription_prompt.md"
        path.write_text(text, encoding="utf-8")
        monkeypatch.setattr(transcription_prompt, "PROMPT_FILE", path)
        monkeypatch.setattr(transcription_prompt, "_cache", None)
        return path

    return _write


def test_comment_lines_are_not_sent_to_the_model(write_prompt):
    write_prompt("# 这是注释\n品牌：马爹利\n\n# 又一行注释\n术语：堆头\n")
    assert load_prompt_text() == "品牌：马爹利\n术语：堆头"


def test_task_context_is_appended_to_the_base_prompt(write_prompt):
    write_prompt("基础提示词\n")
    prompt = build_transcription_prompt(
        build_task_context("建设路烟酒行", "张三")
    )
    assert prompt.startswith("基础提示词")
    assert "建设路烟酒行" in prompt
    assert "张三" in prompt


def test_empty_context_leaves_no_trailing_newline(write_prompt):
    write_prompt("基础提示词\n")
    assert build_transcription_prompt("") == "基础提示词"
    assert build_transcription_prompt(None) == "基础提示词"


def test_task_context_is_empty_when_both_fields_are_blank():
    assert build_task_context("", "   ") == ""
    assert build_task_context(None, None) == ""


def test_missing_file_falls_back_to_the_builtin_default(monkeypatch, tmp_path):
    monkeypatch.setattr(
        transcription_prompt, "PROMPT_FILE", tmp_path / "nope.md"
    )
    monkeypatch.setattr(transcription_prompt, "_cache", None)
    assert load_prompt_text() == DEFAULT_PROMPT_TEXT


def test_comment_only_file_falls_back_to_the_builtin_default(write_prompt):
    write_prompt("# 只有注释\n# 没有正文\n")
    assert load_prompt_text() == DEFAULT_PROMPT_TEXT


def test_prompt_is_truncated_to_the_character_budget(write_prompt):
    write_prompt("第一句话。第二句话很长很长很长很长很长很长很长很长很长。\n")
    prompt = build_transcription_prompt("门店：示例店。", max_chars=25)
    assert len(prompt) <= 25
    assert prompt.endswith("门店：示例店。")


def test_repository_prompt_file_exists_and_is_used():
    assert transcription_prompt.PROMPT_FILE.is_file()
    text = load_prompt_text()
    assert len(text) > 20
    # The shipped prompt must stay inside the budget once task context is added.
    assembled = build_transcription_prompt(
        build_task_context("某烟酒行（某某路店）", "某某某")
    )
    assert len(assembled) <= MAX_PROMPT_CHARS
    assert validate_prompt_file() == []
