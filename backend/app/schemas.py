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
