from io import BytesIO

from openpyxl import Workbook

from app.services.import_service import parse_visit_excel


def test_excel_parser_filters_images_and_keeps_blank_audit_targets():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "拜访数据"
    sheet.append(
        [
            "POI_ID",
            "门店名称",
            "拜访人",
            "录音图片",
            "KEHUVISIT MAIN PICTURE",
            "马爹利今年截止到上个月零售金额(万元)",
            "畅销产品1进货价",
        ]
    )
    sheet.append(["C-1", "测试门店", "测试拜访人", "image-a", "image-b", None, 700])
    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    visits = parse_visit_excel(output)

    assert len(visits) == 1
    fields = visits[0]["fields"]
    assert "录音图片" not in fields
    assert "KEHUVISIT MAIN PICTURE" not in fields
    assert fields["马爹利今年截止到上个月零售金额(万元)"] is None
    assert fields["畅销产品1进货价"] == "700"
