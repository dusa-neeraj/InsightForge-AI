from typing import Any

from pydantic import BaseModel


class UploadResponse(BaseModel):
    dataset_id: str
    filename: str
    report: dict[str, Any]
    preview: list[dict[str, str]]