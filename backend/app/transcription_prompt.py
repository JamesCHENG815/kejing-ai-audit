"""Transcription prompt / hotword assembly.

The prompt lives in ``prompts/transcription_prompt.md`` so that tuning it does
not require a code change or a redeploy. Lines starting with ``#`` are treated
as comments and stripped, which lets the file carry its own documentation.

The file is cached by modification time, so editing it takes effect on the next
transcription without restarting the service.
"""

from __future__ import annotations

import logging
from pathlib import Path


logger = logging.getLogger(__name__)

# Kept dependency-free (standard library only) so the prompt can be validated
# with `python -m app.transcription_prompt` without installing the app's
# requirements. Same value as app.database.BACKEND_DIR.
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROMPTS_DIR = BACKEND_DIR / "prompts"
PROMPT_FILE = PROMPTS_DIR / "transcription_prompt.md"

# OpenAI's transcription prompt is billed as input and long prompts dilute the
# instruction, so the assembled text is capped.
MAX_PROMPT_CHARS = 800

DEFAULT_PROMPT_TEXT = (
    "洋酒经销业务员拜访门店的普通话对话，通常是业务员与店长或老板两人交谈。"
    "行业品牌：马爹利、轩尼诗、人头马。"
    "常见术语：陈列面、堆头、端架、进店价、开单价、返点、搭赠、动销、库存、订货。"
    "数字按说话人原话如实转写，不要换算单位；听不清的地方标注为听不清，不要猜测补全。"
)

_cache: tuple[float, str] | None = None


def _strip_comments(raw: str) -> str:
    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def load_prompt_text() -> str:
    """Return the effective prompt text, falling back to a built-in default."""
    global _cache

    try:
        mtime = PROMPT_FILE.stat().st_mtime
    except OSError:
        return DEFAULT_PROMPT_TEXT

    if _cache is not None and _cache[0] == mtime:
        return _cache[1]

    try:
        raw = PROMPT_FILE.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("无法读取转写提示词文件 %s：%s", PROMPT_FILE, exc)
        return DEFAULT_PROMPT_TEXT

    text = _strip_comments(raw)
    if not text:
        logger.warning("转写提示词文件为空，回退到内置默认值：%s", PROMPT_FILE)
        text = DEFAULT_PROMPT_TEXT

    _cache = (mtime, text)
    return text


def _truncate(text: str, budget: int) -> str:
    if budget <= 0:
        return ""
    if len(text) <= budget:
        return text
    window = text[:budget]
    # Prefer cutting on a sentence boundary so a half sentence is not sent.
    cut = max(window.rfind("。"), window.rfind("\n"))
    return (window[: cut + 1] if cut > budget // 2 else window).strip()


def build_task_context(store: str | None = None, visitor: str | None = None) -> str:
    """Build the per-task hotword tail (store name / sales rep name)."""
    parts: list[str] = []
    if store and store.strip():
        parts.append(f"本店门店名称：{store.strip()}")
    if visitor and visitor.strip():
        parts.append(f"业务员姓名：{visitor.strip()}")
    return "；".join(parts) + "。" if parts else ""


def build_transcription_prompt(
    context: str | None = None, *, max_chars: int = MAX_PROMPT_CHARS
) -> str:
    """Combine the file-based prompt with the per-task hotwords."""
    base = load_prompt_text()
    extra = (context or "").strip()
    if not extra:
        return _truncate(base, max_chars)

    budget = max_chars - len(extra) - 1
    if budget <= 0:
        return extra[:max_chars]
    return f"{_truncate(base, budget)}\n{extra}"


def validate_prompt_file() -> list[str]:
    """Self-check used by ``python -m app.transcription_prompt``."""
    problems: list[str] = []
    if not PROMPT_FILE.is_file():
        problems.append(f"缺少提示词文件：{PROMPT_FILE}")
        return problems

    raw = PROMPT_FILE.read_text(encoding="utf-8")
    body = _strip_comments(raw)
    if not body:
        problems.append("提示词文件只有注释，正文为空")
    full = build_transcription_prompt(
        build_task_context("示例烟酒行（建设路店）", "张三")
    )
    if len(full) > MAX_PROMPT_CHARS:
        problems.append(f"拼接后长度 {len(full)} 超过上限 {MAX_PROMPT_CHARS}")
    return problems


def _main() -> int:
    problems = validate_prompt_file()
    if problems:
        for problem in problems:
            print(f"[FAIL] {problem}")
        return 1
    sample = build_transcription_prompt(
        build_task_context("示例烟酒行（建设路店）", "张三")
    )
    print(f"[OK] 提示词文件：{PROMPT_FILE}")
    print(f"[OK] 拼接后长度：{len(sample)} / {MAX_PROMPT_CHARS} 字符")
    print("--- 模型实际收到的 prompt ---")
    print(sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
