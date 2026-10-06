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