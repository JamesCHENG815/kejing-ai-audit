"""纯标准库的安全辅助函数。

这个模块刻意不导入 fastapi / sqlalchemy 等第三方依赖，方便在没有虚拟环境的
机器上单独运行校验（`python -m app.security` 会执行内置自检）。
"""

from __future__ import annotations

import ipaddress
import re

# 与前端 `MAX_EXCEL` / `MAX_AUDIO` 保持一致；后端是最终防线，不能只靠前端拦。
MAX_EXCEL_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_AUDIO_UPLOAD_BYTES = 100 * 1024 * 1024

# 写入 CSV 后会被 Excel 当成公式执行的起始字符。
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")
_PLAIN_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?%?")


def human_size(byte_count: int) -> str:
    if byte_count >= 1024 * 1024:
        return f"{byte_count / 1024 / 1024:g} MB"
    return f"{max(0, byte_count) / 1024:g} KB"


def csv_safe_cell(value: object) -> str:
    """把单元格转成不会被 Excel 当作公式执行的文本。

    门店名称、修改原因等都来自人工输入，直接写入 CSV 后，以 `=`、`+`、`@`
    开头的值会在经理打开文件时被当作公式求值（CSV Injection）。这里统一加
    一个前导单引号破坏公式语义。

    纯数字（含 `-12.5%` 这类负数与百分比）保持原样，否则导出的负数会退化成
    文本，反而影响核对。
    """
    text = "" if value is None else str(value)
    probe = text.lstrip()
    if not probe:
        return text
    if not probe.startswith(_FORMULA_PREFIXES):
        return text
    if _PLAIN_NUMBER.fullmatch(probe):
        return text
    return f"'{text}"


def is_loopback_host(host: str | None) -> bool:
    """判断请求是否来自本机回环地址。"""
    if not host:
        return False
    candidate = host.strip()
    if candidate.startswith("::ffff:"):
        candidate = candidate[len("::ffff:") :]
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return candidate == "localhost"
    if address.version == 6 and address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_loopback
    return address.is_loopback


def _self_check() -> None:
    cases = {
        "=1+1": "'=1+1",
        "=HYPERLINK(\"http://evil\")": "'=HYPERLINK(\"http://evil\")",
        "+1+1": "'+1+1",
        "-1+1": "'-1+1",
        "@SUM(A1)": "'@SUM(A1)",
        "\t=cmd": "'\t=cmd",
        " =1+1": "' =1+1",
        "-12.5%": "-12.5%",
        "+8": "+8",
        "-3": "-3",
        "宏昌烟酒": "宏昌烟酒",
        "": "",
        "0": "0",
    }
    for raw, expected in cases.items():
        actual = csv_safe_cell(raw)
        assert actual == expected, f"{raw!r}: 期望 {expected!r}，实际 {actual!r}"
    assert human_size(1024) == "1 KB"
    assert human_size(50 * 1024 * 1024) == "50 MB"
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("::1")
    assert is_loopback_host("::ffff:127.0.0.1")
    assert is_loopback_host("localhost")
    assert not is_loopback_host("192.168.1.10")
    assert not is_loopback_host(None)
    print(f"security 自检通过：{len(cases)} 个 CSV 用例 + 6 个地址用例")


if __name__ == "__main__":
    _self_check()
