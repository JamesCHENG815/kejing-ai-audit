from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select

from app.models import (
    AIFieldResult,
    AuditTask,
    ExcelFieldValue,
    ImportBatch,
    Recording,
    TaskRecording,
    TranscriptSegment,
)
from fastapi import HTTPException
from app.services.analysis_service import (
    AnalysisProviderError,
    ExtractedFieldData,
    TranscribedSegmentData,
    analyze_task,
)


LAST_YEAR = "马爹利上一个自然年零售金额(万元)(2025年)"
CURRENT_YEAR = "轩尼诗今年截止到上个月零售金额(万元)"
PRODUCT = "畅销产品1"
GROUP_BUYERS = "团购客户有多少个(经常拿1箱以上任何酒)"
HENNESSY_LAST_YEAR = "轩尼诗上一个自然年零售金额(万元)(2025年)"
REMY_LAST_YEAR = "人头马上一个自然年零售金额(万元)(2025年)"
OCEAN_TOTAL_LAST_YEAR = "三大洋合计上一个自然年零售金额(万元)(2025年)"


def ocean_share_field(brand):
    return f"{brand}占三大洋上一个自然年零售金额(万元)(2025年)比例(%)"


class FakeProvider:
    transcribe_calls = 0
    extract_calls = 0

    def transcribe(self, _audio_path):
        self.transcribe_calls += 1
        return [
            TranscribedSegmentData(0, 5, "业务员", "去年马爹利卖了多少？"),
            TranscribedSegmentData(5, 10, "门店", "去年马爹利大概二十万。"),
            TranscribedSegmentData(10, 15, "门店", "轩尼诗今年到上个月是十二万。"),
            TranscribedSegmentData(15, 20, "门店", "卖得最好的是马爹利蓝带。"),
        ]

    def extract_fields(self, _targets, _transcript):
        self.extract_calls += 1
        return [
            ExtractedFieldData(LAST_YEAR, "20", "万元", 0.95, 1, 1),
            ExtractedFieldData(CURRENT_YEAR, "12", "万元", 0.94, 1, 2),
            ExtractedFieldData(PRODUCT, "马爹利蓝带", None, 0.60, 1, 3),
            # Invalid field and invalid evidence references must never be persisted.
            ExtractedFieldData("录音图片", "fake-image", None, 0.99, 1, 0),
            ExtractedFieldData(GROUP_BUYERS, "99", "个", 0.99, 99, 0),
        ]


class FailingExtractionProvider(FakeProvider):
    def extract_fields(self, _targets, _transcript):
        raise AnalysisProviderError("字段提取失败")


class OceanSplitProvider:
    def __init__(self, recording_id, shares=("50", "30", "20"), total="100"):
        self.recording_id = recording_id
        self.shares = shares
        self.total = total

    def transcribe(self, _audio_path):
        return [
            TranscribedSegmentData(0, 5, "门店", f"去年三大洋合计{self.total}万。"),
            TranscribedSegmentData(5, 10, "门店", f"马爹利占{self.shares[0]}%。"),
            TranscribedSegmentData(10, 15, "门店", f"轩尼诗占{self.shares[1]}%。"),
            TranscribedSegmentData(15, 20, "门店", f"人头马占{self.shares[2]}%。"),
        ]

    def extract_fields(self, targets, _transcript):
        target_names = {name for name, _unit in targets}
        expected_intermediates = {
            OCEAN_TOTAL_LAST_YEAR,
            *(ocean_share_field(brand) for brand in ("马爹利", "轩尼诗", "人头马")),
        }
        assert expected_intermediates <= target_names
        return [
            ExtractedFieldData(
                OCEAN_TOTAL_LAST_YEAR, self.total, "万元", 0.96,
                self.recording_id, 0,
            ),
            *(
                ExtractedFieldData(
                    ocean_share_field(brand), share, "%", 0.95,
                    self.recording_id, index,
                )
                for index, (brand, share) in enumerate(
                    zip(("马爹利", "轩尼诗", "人头马"), self.shares),
                    start=1,
                )
            ),
        ]


class IncompleteOceanSplitProvider(OceanSplitProvider):
    def extract_fields(self, targets, transcript):
        return [
            item
            for item in super().extract_fields(targets, transcript)
            if item.field_name != ocean_share_field("人头马")
        ]


def create_pending_task(db_session):
    batch = ImportBatch(
        original_filename="real.xlsx",
        file_path="storage/imports/1/real.xlsx",
        status="submitted",
    )
    task = AuditTask(
        import_batch=batch,
        customer_id="C-1",
        store_name="测试门店",
        visitor="测试拜访人",
        status="pending_analysis",
    )
    task.excel_values = [
        ExcelFieldValue(field_name=LAST_YEAR, field_value="20"),
        ExcelFieldValue(field_name=CURRENT_YEAR, field_value="10"),
        ExcelFieldValue(field_name=PRODUCT, field_value="马爹利蓝带"),
        ExcelFieldValue(field_name=GROUP_BUYERS, field_value="3"),
        ExcelFieldValue(field_name="录音图片", field_value="image-id"),
    ]
    recording = Recording(
        import_batch=batch,
        original_filename="real.m4a",
        file_path=f"storage/recordings/tests/{uuid4().hex}.m4a",
        status="queued",
    )
    task.task_recordings = [
        TaskRecording(
            recording=recording,
            is_recommended=True,
            is_confirmed=True,
        )
    ]
    db_session.add(batch)
    db_session.commit()
    return task, recording


def test_analysis_persists_transcript_evidence_and_all_statuses(db_session):
    task, recording = create_pending_task(db_session)
    provider = FakeProvider()

    result = analyze_task(db_session, task.id, provider)

    assert result.transcript_segment_count == 4
    assert result.ai_result_count == 47
    assert (result.matched, result.pending, result.conflict, result.missing) == (1, 1, 1, 44)
    assert db_session.scalar(
        select(func.count()).select_from(TranscriptSegment)
    ) == 4
    results = {
        item.field_name: item
        for item in db_session.scalars(
            select(AIFieldResult).where(AIFieldResult.task_id == task.id)
        )
    }
    assert len(results) == 47
    assert {LAST_YEAR, CURRENT_YEAR, PRODUCT, GROUP_BUYERS} <= set(results)
    assert results[LAST_YEAR].status == "matched"
    assert results[LAST_YEAR].evidence_recording_id == recording.id
    assert results[LAST_YEAR].evidence_start_seconds == 5
    assert results[LAST_YEAR].evidence_end_seconds == 10
    assert results[LAST_YEAR].evidence_text == "去年马爹利大概二十万。"
    assert results[CURRENT_YEAR].status == "conflict"
    assert results[PRODUCT].status == "pending"
    assert results[GROUP_BUYERS].status == "missing"
    assert results[GROUP_BUYERS].field_value is None
    assert db_session.get(AuditTask, task.id).status == "pending"
    assert db_session.get(ImportBatch, task.import_batch_id).status == "analyzed"


def test_analysis_reuses_existing_transcript_without_retranscribing(db_session):
    task, recording = create_pending_task(db_session)
    recording.transcript_segments = [
        TranscriptSegment(start_seconds=5, end_seconds=10, speaker="门店", text="去年马爹利大概二十万。")
    ]
    db_session.commit()
    provider = FakeProvider()

    analyze_task(db_session, task.id, provider)

    assert provider.transcribe_calls == 0
    assert provider.extract_calls == 1


def test_analysis_keeps_paid_transcript_when_extraction_fails(db_session):
    task, recording = create_pending_task(db_session)

    try:
        analyze_task(db_session, task.id, FailingExtractionProvider())
    except AnalysisProviderError:
        pass
    else:
        raise AssertionError("extraction failure should propagate")

    assert db_session.scalar(
        select(func.count()).select_from(TranscriptSegment)
    ) == 4
    assert db_session.scalar(select(func.count()).select_from(AIFieldResult)) == 0
    assert db_session.get(Recording, recording.id).status == "transcribed"
    assert db_session.get(AuditTask, task.id).status == "pending_analysis"


def test_analysis_rejects_task_without_recording(db_session):
    batch = ImportBatch(
        original_filename="no-audio.xlsx",
        file_path="storage/imports/tests/no-audio.xlsx",
        status="submitted",
    )
    task = AuditTask(
        import_batch=batch,
        customer_id="C-2",
        store_name="无录音门店",
        visitor="测试拜访人",
        status="pending_analysis",
    )
    db_session.add(batch)
    db_session.commit()

    try:
        analyze_task(db_session, task.id, FakeProvider())
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "没有关联录音" in exc.detail
    else:
        raise AssertionError("task without recordings should not be analyzed")


def test_analysis_splits_ocean_total_by_complete_brand_shares(db_session):
    task, recording = create_pending_task(db_session)
    next(item for item in task.excel_values if item.field_name == LAST_YEAR).field_value = "50"
    task.excel_values.extend(
        [
            ExcelFieldValue(field_name=HENNESSY_LAST_YEAR, field_value="30"),
            ExcelFieldValue(field_name=REMY_LAST_YEAR, field_value="20"),
        ]
    )
    db_session.commit()

    analyze_task(db_session, task.id, OceanSplitProvider(recording.id))

    results = {
        item.field_name: item
        for item in db_session.scalars(
            select(AIFieldResult).where(AIFieldResult.task_id == task.id)
        )
    }
    assert results[LAST_YEAR].field_value == "50"
    assert results[HENNESSY_LAST_YEAR].field_value == "30"
    assert results[REMY_LAST_YEAR].field_value == "20"
    assert all(
        results[name].status == "matched"
        for name in (LAST_YEAR, HENNESSY_LAST_YEAR, REMY_LAST_YEAR)
    )
    assert OCEAN_TOTAL_LAST_YEAR not in results
    assert ocean_share_field("马爹利") not in results
    assert results[LAST_YEAR].evidence_text == "去年三大洋合计100万。 马爹利占50%。"


def test_analysis_does_not_split_when_brand_shares_do_not_total_100(db_session):
    task, recording = create_pending_task(db_session)

    analyze_task(
        db_session,
        task.id,
        OceanSplitProvider(recording.id, shares=("50", "30", "10")),
    )

    results = {
        item.field_name: item
        for item in db_session.scalars(
            select(AIFieldResult).where(AIFieldResult.task_id == task.id)
        )
    }
    assert results[LAST_YEAR].field_value is None
    assert results[HENNESSY_LAST_YEAR].field_value is None
    assert results[REMY_LAST_YEAR].field_value is None
    assert all(
        results[name].status == "pending"
        for name in (LAST_YEAR, HENNESSY_LAST_YEAR, REMY_LAST_YEAR)
    )


def test_analysis_marks_incomplete_brand_shares_pending(db_session):
    task, recording = create_pending_task(db_session)

    analyze_task(
        db_session,
        task.id,
        IncompleteOceanSplitProvider(recording.id),
    )

    results = {
        item.field_name: item
        for item in db_session.scalars(
            select(AIFieldResult).where(AIFieldResult.task_id == task.id)
        )
    }
    assert all(
        results[name].field_value is None
        and results[name].status == "pending"
        for name in (LAST_YEAR, HENNESSY_LAST_YEAR, REMY_LAST_YEAR)
    )


def test_analysis_rounds_split_amounts_half_up_to_two_decimals(db_session):
    task, recording = create_pending_task(db_session)

    analyze_task(
        db_session,
        task.id,
        OceanSplitProvider(
            recording.id,
            shares=("33.335", "33.335", "33.33"),
        ),
    )

    results = {
        item.field_name: item
        for item in db_session.scalars(
            select(AIFieldResult).where(AIFieldResult.task_id == task.id)
        )
    }
    assert results[LAST_YEAR].field_value == "33.34"
    assert results[HENNESSY_LAST_YEAR].field_value == "33.34"
    assert results[REMY_LAST_YEAR].field_value == "33.33"
