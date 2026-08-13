from app.field_rules import (
    EvidenceValue,
    determine_field_status,
    evidence_context_is_sufficient,
    evidence_supports_value,
    is_auditable_field,
    is_image_field,
    required_audit_field_names,
    values_equal,
)


AMOUNT_FIELD = "马爹利上一个自然年零售金额(万元)(2025年)"


def test_amount_expressions_compare_in_same_unit():
    assert values_equal(AMOUNT_FIELD, "20", "20万")
    assert values_equal(AMOUNT_FIELD, "20万元", "二十万")
    assert values_equal(AMOUNT_FIELD, "20", "二十万元")
    assert values_equal(AMOUNT_FIELD, "20", "200000元")
    assert not values_equal(AMOUNT_FIELD, "20", "30万")
    assert not values_equal("畅销产品1", "麦卡伦12年", "格兰菲迪12年")
    assert values_equal("这些宴会是否有洋酒需求", "是", "有需求")
    assert values_equal("这些宴会是否有洋酒需求", "否", "不需要")


def test_status_rules_are_deterministic():
    evidence = EvidenceValue(1, 12.5, 17.0, "马爹利去年卖了二十万")
    assert determine_field_status(
        AMOUNT_FIELD, "20", "二十万", 0.95, evidence
    ) == "matched"
    assert determine_field_status(
        AMOUNT_FIELD, "20", "二十万", 0.70, evidence
    ) == "pending"
    assert determine_field_status(
        AMOUNT_FIELD, "20", "30万", 0.95, evidence
    ) == "conflict"
    assert determine_field_status(
        AMOUNT_FIELD, "20", None, 0, None
    ) == "missing"


def test_auditable_fields_include_requirements_and_exclude_images():
    assert is_auditable_field(AMOUNT_FIELD)
    assert is_auditable_field("畅销产品10进货价")
    assert is_auditable_field("团购客户有多少个(经常拿1箱以上任何酒)")
    assert is_auditable_field("门店同比（今年对比去年销售额）增减")
    assert is_auditable_field("比例（%）")
    assert is_image_field("录音图片")
    assert is_image_field("KEHUVISIT MAIN PICTURE")
    assert not is_auditable_field("录音图片")
    assert not is_auditable_field("地址")


def test_required_fields_preserve_source_reporting_year():
    fields = required_audit_field_names(
        2030, ["马爹利上一个自然年零售金额(万元)(2025年)"]
    )
    assert "轩尼诗上一个自然年零售金额(万元)(2025年)" in fields
    assert "2025年度宴会场次(含白酒)" in fields
    assert "轩尼诗上一个自然年零售金额(万元)(2029年)" not in fields


def test_evidence_must_directly_support_extracted_value():
    assert evidence_supports_value(
        AMOUNT_FIELD,
        "20",
        "万元",
        "去年大概二十万",
        "马爹利去年的销售额大概二十万",
    )
    assert evidence_supports_value("畅销产品1产品瓶数", "12", "瓶", "蓝带卖了12瓶")
    assert evidence_supports_value("畅销产品1", "马爹利蓝带", None, "马爹利蓝带卖得最好")
    assert evidence_supports_value("这些宴会是否有洋酒需求", "是", None, "这些宴会有洋酒需求")
    assert not evidence_supports_value(
        AMOUNT_FIELD,
        "30",
        "万元",
        "去年大概二十万",
        "马爹利去年的销售额大概二十万",
    )
    assert not evidence_supports_value("畅销产品1", "人头马特级", None, "马爹利蓝带卖得最好")


def test_evidence_rejects_questions_categories_and_wrong_time_scope():
    assert not evidence_supports_value(
        "畅销产品2", "白酒", None, "今年上半年白酒能卖到多少?"
    )
    assert evidence_supports_value(
        "马爹利今年截止到上个月零售金额(万元)",
        "85",
        "万元",
        "八十五万",
        "马爹利今年上半年能卖几万？八十五万。",
    )
    assert not evidence_context_is_sufficient(
        "马爹利今年截止到上个月零售金额(万元)",
        "马爹利今年上半年能卖几万？八十五万。",
    )
    assert evidence_supports_value(
        "人头马上一个自然年零售金额(万元)(2025年)",
        "20",
        "万元",
        "能有二十万左右吧",
        "像人头马的话，去年来说一整年能卖多少万？能有二十万左右吧。",
    )
    assert evidence_context_is_sufficient(
        "人头马上一个自然年零售金额(万元)(2025年)",
        "像人头马的话，去年来说一整年能卖多少万？能有二十万左右吧。",
    )
    assert not evidence_context_is_sufficient(
        "畅销产品2", "洋金的南带进货价应该一百六十三"
    )
