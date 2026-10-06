from typing import Any

from pydantic import BaseModel, Field, field_validator


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