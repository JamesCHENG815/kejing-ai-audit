from pydantic import BaseModel, ConfigDict, Field


class RecordingMatch(BaseModel):
    id: int
    filename: str
    recommended: bool
    confirmed: bool


class TaskMatch(BaseModel):
    id: int
    customer_id: str
    store_name: str
    visitor: str
    recordings: list[RecordingMatch]


class BatchMatchesResponse(BaseModel):
    batch_id: int
    status: str
    tasks: list[TaskMatch]
    unassigned_recordings: list[RecordingMatch]


class MatchAssignment(BaseModel):
    recording_id: int
    task_id: int
    confirmed: bool = True


class UpdateMatchesRequest(BaseModel):
    assignments: list[MatchAssignment] = Field(min_length=1)


class BatchCreatedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    status: str
    task_count: int


class RecordingsUploadedResponse(BaseModel):
    batch_id: int
    uploaded_count: int
    matched_count: int


class SubmitBatchResponse(BaseModel):
    batch_id: int
    status: str
    task_count: int
    recording_count: int


class ReviewStats(BaseModel):
    matched: int = 0
    pending: int = 0
    conflict: int = 0
    missing: int = 0


class ReviewTaskResponse(BaseModel):
    id: str
    batch_id: int = Field(serialization_alias="batchId")
    customer_id: str = Field(serialization_alias="customerId")
    store: str
    visitor: str
    status: str
    has_recording: bool = Field(serialization_alias="hasRecording")
    updated_at: str = Field(serialization_alias="updatedAt")
    stats: ReviewStats
    address: str = "—"
    visit_date: str = Field(default="—", serialization_alias="visitDate")


class ReviewEvidence(BaseModel):
    recording_id: str = Field(serialization_alias="recordingId")
    start: float
    end: float
    text: str


class ReviewFieldResponse(BaseModel):
    key: str
    label: str
    excel: str
    ai: str
    unit: str | None = None
    confidence: float
    status: str
    final: str
    reason: str
    confirmed: bool
    evidence: ReviewEvidence | None = None


class ReviewRecordingResponse(BaseModel):
    id: str
    name: str
    duration: float
    url: str


class ReviewTranscriptResponse(BaseModel):
    recording_id: str = Field(serialization_alias="recordingId")
    time: float
    speaker: str
    text: str
    evidence: bool = False


class ReviewHistoryResponse(BaseModel):
    who: str
    when: str
    action: str
    kind: str = "event"
    field: str | None = None
    before: str | None = None
    after: str | None = None
    reason: str | None = None


class ReviewTaskDetailResponse(BaseModel):
    task: ReviewTaskResponse
    fields: list[ReviewFieldResponse]
    recordings: list[ReviewRecordingResponse]
    transcripts: list[ReviewTranscriptResponse]
    history: list[ReviewHistoryResponse]
    has_ai_analysis: bool = Field(serialization_alias="hasAiAnalysis")
    has_transcript: bool = Field(serialization_alias="hasTranscript")


class ReviewFieldInput(BaseModel):
    key: str
    final: str = ""
    reason: str = ""
    confirmed: bool = False


class SaveReviewRequest(BaseModel):
    fields: list[ReviewFieldInput]
    reviewer: str = "当前经理"


class SaveReviewResponse(BaseModel):
    task_id: str = Field(serialization_alias="taskId")
    status: str
    confirmed_count: int = Field(serialization_alias="confirmedCount")
    field_count: int = Field(serialization_alias="fieldCount")


class AnalyzeTaskRequest(BaseModel):
    force: bool = False


class AnalyzeTaskResponse(BaseModel):
    task_id: int
    status: str
    recording_count: int
    transcript_segment_count: int
    ai_result_count: int
    matched: int
    pending: int
    conflict: int
    missing: int


class AnalyzePendingRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    force: bool = False
    batch_id: int | None = Field(default=None, ge=1)


class AnalyzePendingResponse(BaseModel):
    requested_count: int
    completed_count: int
    results: list[AnalyzeTaskResponse]
