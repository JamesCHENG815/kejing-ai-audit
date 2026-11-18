from __future__ import annotations

import pytest

from app.security import csv_safe_cell, human_size, is_loopback_host


@pytest.mark.parametrize(
    "raw",
    [
        "=1+1",
        "=HYPERLINK(\"http://example.com\")",
        "+1+1",
        "-1+1",
        "@SUM(A1)",
        "\t=cmd",
        "\r=cmd",
        " =1+1",
        "  @SUM(1)",
    ],
)
def test_formula_like_cells_are_escaped(raw):
    assert csv_safe_cell(raw).startswith("'")


@pytest.mark.parametrize("raw", ["-12.5%", "+8", "-3", "0", "47.25"])
def test_plain_numbers_keep_their_type(raw):
    # 负数与百分比如果也被加上单引号，导出的金额/占比会退化成文本。
    assert csv_safe_cell(raw) == raw


@pytest.mark.parametrize(
    "raw", ["宏昌烟酒", "马爹利蓝带", "", "数据缺失", "门店同比-12%"]
)
def test_ordinary_text_is_untouched(raw):
    assert csv_safe_cell(raw) == raw


def test_none_becomes_empty_string():
    assert csv_safe_cell(None) == ""


def test_human_size():
    assert human_size(512 * 1024) == "512 KB"
    assert human_size(50 * 1024 * 1024) == "50 MB"


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("::ffff:127.0.0.1", True),
        ("localhost", True),
        ("192.168.1.10", False),
        ("10.0.0.5", False),
        ("testclient", False),
        (None, False),
    ],
)
def test_is_loopback_host(host, expected):
    assert is_loopback_host(host) is expected
