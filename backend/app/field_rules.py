from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


IMAGE_FIELD_MARKERS = (
    "图片",
    "照片",
    "影像",
    "picture",
    "photo",
    "image",
)
SALES_BRANDS = ("马爹利", "轩尼诗", "人头马", "白酒", "威士忌")
PRODUCT_CATEGORY_NAMES = {"白酒", "洋酒", "威士忌", "红酒", "啤酒", "酒"}
LOW_CONFIDENCE_THRESHOLD = 0.75
OTHER_AUDIT_FIELDS = (
    "门店同比（今年对比去年销售额）增减",
    "比例（%）",
    "{year}年度宴会场次(含白酒)",
    "未来6周有几场消费者的宴会",
    "这些宴会是否有洋酒需求",
    "团购客户有多少个(经常拿1箱以上任何酒)",
    "上月洋酒一共售卖了多少瓶",
)


@dataclass(frozen=True)
class EvidenceValue:
    recording_id: int
    start_seconds: float
    end_seconds: float
    text: str


def is_image_field(field_name: str) -> bool:
    normalized = unicodedata.normalize("NFKC", field_name).casefold()
    return any(marker in normalized for marker in IMAGE_FIELD_MARKERS)


def is_auditable_field(field_name: str) -> bool:
    if is_image_field(field_name):
        return False
    normalized = unicodedata.normalize("NFKC", field_name).strip()
    if any(brand in normalized for brand in SALES_BRANDS) and (
        "上一个自然年零售金额" in normalized
        or "去年销售额" in normalized
        or "今年截止到上个月零售金额" in normalized
        or "今年截至上月销售额" in normalized
    ):
        return True
    if re.fullmatch(r"畅销产品\d+(?:产品瓶数|进货价)?", normalized):
        return True
    return any(
        marker in normalized
        for marker in (
            "年度宴会场次",
            "门店同比",
            "比例",
            "未来6周有几场消费者的宴会",
            "这些宴会是否有洋酒需求",
            "团购客户有多少个",
            "上月洋酒一共售卖了多少瓶",
        )
    )


def required_audit_field_names(
    task_year: int, existing_names: list[str] | tuple[str, ...]
) -> list[str]:
    """Return the complete ordered extraction target set, including blank Excel cells."""
    previous_year = task_year - 1
    for name in existing_names:
        year_match = re.search(
            r"上一个自然年零售金额.*?\((\d{4})年\)", name
        )
        if year_match:
            previous_year = int(year_match.group(1))
            break
    required = [
        f"{brand}上一个自然年零售金额(万元)({previous_year}年)"
        for brand in SALES_BRANDS
    ]
    required.extend(
        f"{brand}今年截止到上个月零售金额(万元)" for brand in SALES_BRANDS
    )
    for index in range(1, 11):
        required.extend(
            (
                f"畅销产品{index}",
                f"畅销产品{index}产品瓶数",
                f"畅销产品{index}进货价",
            )
        )
    required.extend(
        field.format(year=previous_year) for field in OTHER_AUDIT_FIELDS
    )
    # Keep source header spelling/order when the Excel has additional supported fields.
    required.extend(name for name in existing_names if is_auditable_field(name))
    return list(dict.fromkeys(required))


def infer_unit(field_name: str, stored_unit: str | None = None) -> str | None:
    if stored_unit:
        return stored_unit
    normalized = unicodedata.normalize("NFKC", field_name)
    if "金额(万元)" in normalized or "销售额" in normalized:
        return "万元"
    if "进货价" in normalized:
        return "元"
    if "瓶数" in normalized or "多少瓶" in normalized:
        return "瓶"
    if "场次" in normalized or "几场" in normalized:
        return "场"
    if "客户有多少个" in normalized:
        return "个"
    if "比例" in normalized:
        return "%"
    return None


def _parse_chinese_integer(value: str) -> Decimal | None:
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3,
              "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    small_units = {"十": 10, "百": 100, "千": 1000}
    large_units = {"万": 10_000, "亿": 100_000_000}
    if not value or any(char not in digits | small_units | large_units for char in value):
        return None
    total = 0
    section = 0
    number = 0
    for char in value:
        if char in digits:
            number = digits[char]
        elif char in small_units:
            section += (number or 1) * small_units[char]
            number = 0
        else:
            section += number
            total += section * large_units[char]
            section = 0
            number = 0
    return Decimal(total + section + number)


def _parse_chinese_decimal(value: str) -> Decimal | None:
    if "点" not in value:
        return _parse_chinese_integer(value)
    integer, fraction = value.split("点", 1)
    integer_value = _parse_chinese_integer(integer) or Decimal(0)
    digit_map = {"零": "0", "〇": "0", "一": "1", "二": "2", "两": "2",
                 "三": "3", "四": "4", "五": "5", "六": "6", "七": "7",
                 "八": "8", "九": "9"}
    if not fraction or any(char not in digit_map for char in fraction):
        return None
    return integer_value + Decimal(f"0.{''.join(digit_map[char] for char in fraction)}")


def _numeric_value(value: str, unit: str | None) -> Decimal | None:
    normalized = unicodedata.normalize("NFKC", value).strip().replace(",", "")
    multiplier = Decimal(1)
    if "亿" in normalized:
        multiplier = Decimal(100_000_000)
    elif "万" in normalized:
        multiplier = Decimal(10_000)
    numeric_match = re.search(r"[-+]?\d+(?:\.\d+)?", normalized)
    number: Decimal | None = None
    if numeric_match:
        try:
            number = Decimal(numeric_match.group())
        except InvalidOperation:
            return None
    else:
        chinese_match = re.search(r"[零〇一二两三四五六七八九十百千万亿点]+", normalized)
        if chinese_match:
            chinese_text = chinese_match.group()
            if multiplier != 1 and chinese_text[-1:] in {"万", "亿"}:
                chinese_text = chinese_text[:-1]
            number = _parse_chinese_decimal(chinese_text)
    if number is None:
        return None
    if multiplier == 1 and unit == "万元" and "元" not in normalized:
        multiplier = Decimal(10_000)
    return number * multiplier


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\s,，。.!！?？、·'\"“”‘’()（）\[\]【】_-]+", "", normalized)


def _boolean_value(value: str) -> bool | None:
    normalized = _normalized_text(value)
    negatives = ("否", "没有", "无", "不需要", "没需求", "不需求")
    positives = ("是", "有", "需要", "有需求", "需求")
    if any(marker in normalized for marker in negatives):
        return False
    if any(marker in normalized for marker in positives):
        return True
    return None


def evidence_supports_value(
    field_name: str,
    value: str,
    unit: str | None,
    evidence_text: str,
    context_text: str | None = None,
) -> bool:
    normalized_evidence = _normalized_text(evidence_text)
    normalized_context = _normalized_text(context_text or evidence_text)
    if evidence_text.rstrip().endswith(("?", "？")) or any(
        marker in normalized_evidence
        for marker in ("多少", "几万", "什么价", "多少钱")
    ):
        return False
    if re.fullmatch(r"畅销产品\d+", field_name) and _normalized_text(value) in {
        _normalized_text(name) for name in PRODUCT_CATEGORY_NAMES
    }:
        return False
    if "是否" in field_name or "需求" in field_name:
        expected_boolean = _boolean_value(value)
        evidence_boolean = _boolean_value(evidence_text)
        return expected_boolean is not None and expected_boolean == evidence_boolean
    inferred = infer_unit(field_name, unit)
    numeric_units = {"元", "万元", "瓶", "场", "个", "%"}
    if inferred in numeric_units:
        expected = _numeric_value(value, inferred)
        if expected is None:
            return False
        candidates = re.findall(
            r"[-+]?\d+(?:\.\d+)?\s*(?:亿|万)?\s*(?:万元|元|瓶|场|个|%)?"
            r"|[零〇一二两三四五六七八九十百千万亿点]+\s*(?:万元|元|瓶|场|个)?",
            unicodedata.normalize("NFKC", evidence_text),
        )
        return any(
            _numeric_value(candidate, inferred) == expected
            for candidate in candidates
        )
    return _normalized_text(value) in _normalized_text(evidence_text)


def evidence_context_is_sufficient(field_name: str, context_text: str) -> bool:
    """Whether nearby transcript context is strong enough for an automatic verdict."""
    normalized = _normalized_text(context_text)
    if re.fullmatch(r"畅销产品\d+", field_name):
        return any(
            marker in normalized
            for marker in ("畅销", "卖得好", "卖得最好", "主卖", "走量", "销量最好")
        )
    if re.fullmatch(r"畅销产品\d+进货价", field_name):
        return "进货" in normalized and any(
            marker in normalized for marker in ("价", "块", "元")
        )
    if re.fullmatch(r"畅销产品\d+产品瓶数", field_name):
        return "上月" in normalized and "瓶" in normalized
    brand = next((name for name in SALES_BRANDS if field_name.startswith(name)), None)
    if brand and brand not in normalized:
        return False
    if "上一个自然年零售金额" in field_name:
        return any(
            marker in normalized for marker in ("去年", "上一个自然年", "一整年", "全年")
        )
    if "今年截止到上个月零售金额" in field_name:
        return any(
            marker in normalized for marker in ("截止到上个月", "截至上月", "到上个月")
        )
    return True


def values_equal(
    field_name: str,
    excel_value: str | None,
    ai_value: str | None,
    *,
    excel_unit: str | None = None,
    ai_unit: str | None = None,
) -> bool:
    if excel_value in (None, "") or ai_value in (None, ""):
        return False
    inferred = infer_unit(field_name, excel_unit)
    if "是否" in field_name or "需求" in field_name:
        left_boolean = _boolean_value(str(excel_value))
        right_boolean = _boolean_value(str(ai_value))
        if left_boolean is not None and right_boolean is not None:
            return left_boolean == right_boolean
    numeric_units = {"元", "万元", "瓶", "场", "个", "%"}
    if inferred in numeric_units or ai_unit in numeric_units:
        left_number = _numeric_value(str(excel_value), inferred)
        right_number = _numeric_value(str(ai_value), ai_unit or inferred)
        if left_number is not None and right_number is not None:
            return left_number == right_number
    return _normalized_text(str(excel_value)) == _normalized_text(str(ai_value))


def determine_field_status(
    field_name: str,
    excel_value: str | None,
    ai_value: str | None,
    confidence: float | None,
    evidence: EvidenceValue | None,
    *,
    excel_unit: str | None = None,
    ai_unit: str | None = None,
    confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
) -> str:
    if ai_value in (None, ""):
        return "missing"
    evidence_is_valid = bool(
        evidence
        and evidence.text.strip()
        and evidence.end_seconds >= evidence.start_seconds >= 0
    )
    if not evidence_is_valid or confidence is None or confidence < confidence_threshold:
        return "pending"
    if excel_value in (None, ""):
        return "pending"
    return (
        "matched"
        if values_equal(
            field_name,
            excel_value,
            ai_value,
            excel_unit=excel_unit,
            ai_unit=ai_unit,
        )
        else "conflict"
    )
