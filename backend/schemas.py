from typing import Any

from pydantic import BaseModel


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