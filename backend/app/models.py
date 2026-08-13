from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ImportBatch(TimestampMixin, Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="uploaded", nullable=False)

    tasks: Mapped[list["AuditTask"]] = relationship(
        back_populates="import_batch", cascade="all, delete-orphan"
    )
    recordings: Mapped[list["Recording"]] = relationship(
        back_populates="import_batch", cascade="all, delete-orphan"
    )


class AuditTask(TimestampMixin, Base):
    __tablename__ = "audit_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    store_name: Mapped[str] = mapped_column(String(255), nullable=False)
    visitor: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)

    import_batch: Mapped["ImportBatch"] = relationship(back_populates="tasks")
    task_recordings: Mapped[list["TaskRecording"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    excel_values: Mapped[list["ExcelFieldValue"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    ai_results: Mapped[list["AIFieldResult"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    human_reviews: Mapped[list["HumanReview"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class Recording(TimestampMixin, Base):
    __tablename__ = "recordings"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="uploaded", nullable=False)

    import_batch: Mapped["ImportBatch"] = relationship(back_populates="recordings")
    task_recordings: Mapped[list["TaskRecording"]] = relationship(
        back_populates="recording", cascade="all, delete-orphan"
    )
    transcript_segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="recording", cascade="all, delete-orphan"
    )


class TaskRecording(TimestampMixin, Base):
    __tablename__ = "task_recordings"
    __table_args__ = (UniqueConstraint("task_id", "recording_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("audit_tasks.id", ondelete="CASCADE"), index=True
    )
    recording_id: Mapped[int] = mapped_column(
        ForeignKey("recordings.id", ondelete="CASCADE"), index=True
    )
    is_recommended: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    task: Mapped["AuditTask"] = relationship(back_populates="task_recordings")
    recording: Mapped["Recording"] = relationship(back_populates="task_recordings")


class ExcelFieldValue(TimestampMixin, Base):
    __tablename__ = "excel_field_values"
    __table_args__ = (UniqueConstraint("task_id", "field_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("audit_tasks.id", ondelete="CASCADE"), index=True
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(30))

    task: Mapped["AuditTask"] = relationship(back_populates="excel_values")


class TranscriptSegment(TimestampMixin, Base):
    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    recording_id: Mapped[int] = mapped_column(
        ForeignKey("recordings.id", ondelete="CASCADE"), index=True
    )
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    speaker: Mapped[str | None] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text, nullable=False)

    recording: Mapped["Recording"] = relationship(back_populates="transcript_segments")


class AIFieldResult(TimestampMixin, Base):
    __tablename__ = "ai_field_results"
    __table_args__ = (UniqueConstraint("task_id", "field_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("audit_tasks.id", ondelete="CASCADE"), index=True
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(30))
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    evidence_recording_id: Mapped[int | None] = mapped_column(
        ForeignKey("recordings.id", ondelete="SET NULL")
    )
    evidence_start_seconds: Mapped[float | None] = mapped_column(Float)
    evidence_end_seconds: Mapped[float | None] = mapped_column(Float)
    evidence_text: Mapped[str | None] = mapped_column(Text)

    task: Mapped["AuditTask"] = relationship(back_populates="ai_results")


class HumanReview(TimestampMixin, Base):
    __tablename__ = "human_reviews"
    __table_args__ = (UniqueConstraint("task_id", "field_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("audit_tasks.id", ondelete="CASCADE"), index=True
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    final_value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(30))
    change_reason: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(String(100))

    task: Mapped["AuditTask"] = relationship(back_populates="human_reviews")
