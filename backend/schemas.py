from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class UploadResponse(BaseModel):
    dataset_id: str
    filename: str
    report: dict[str, Any]
    preview: list[dict[str, str]]


class ProfileResponse(BaseModel):
    dataset_id: str
    version: str
    profile: dict[str, Any]


class QualityResponse(BaseModel):
    dataset_id: str
    quality: dict[str, Any]


class EDAResponse(BaseModel):
    dataset_id: str
    eda: dict[str, Any]


class ChartsResponse(BaseModel):
    dataset_id: str
    charts: list[dict[str, Any]]
    skipped: list[dict[str, str]]
    counts: dict[str, int]


class KPIResponse(BaseModel):
    dataset_id: str
    kpis: dict[str, Any]


class InsightsResponse(BaseModel):
    dataset_id: str
    insights: list[dict[str, Any]]
    narration: dict[str, Any]
    roles: dict[str, Any]
    cached: bool


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    session_id: str | None = None

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("The question cannot be empty.")
        return value


class ChatResponse(BaseModel):
    dataset_id: str
    session_id: str
    question: str
    status: str
    answer: str
    method: list[str]
    plan: dict[str, Any] | None
    result: dict[str, Any] | None
    source: str
    note: str | None
    suggestions: list[str]


class ChatHistoryResponse(BaseModel):
    dataset_id: str
    session_id: str
    turns: list[dict[str, Any]]


class SqlRequest(BaseModel):
    question: str | None = Field(default=None, max_length=500)
    sql: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def exactly_one(self):
        question = (self.question or "").strip()
        sql = (self.sql or "").strip()
        if bool(question) == bool(sql):
            raise ValueError("Send either a question or SQL, not both and not neither.")
        self.question = question or None
        self.sql = sql or None
        return self


class SqlResponse(BaseModel):
    dataset_id: str
    status: str  # ok | rejected | error | unsupported
    source: str  # user | ai | rules
    question: str | None
    sql: str | None
    explanation: str | None
    message: str | None
    note: str | None
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int


class SqlSchemaResponse(BaseModel):
    dataset_id: str
    table: str
    rows: int
    columns: list[dict[str, Any]]
    notes: list[str]


class PreviewResponse(BaseModel):
    dataset_id: str
    columns: list[str]
    total_rows: int
    rows: list[list[Any]]