import math

import pandas as pd
from fastapi import APIRouter, Query

from schemas import PreviewResponse
from services import file_service

router = APIRouter(prefix="/datasets", tags=["Datasets"])


def _cell(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        has_time = value != value.normalize()
        return value.strftime("%Y-%m-%d %H:%M:%S" if has_time else "%Y-%m-%d")
    if hasattr(value, "item"):  # numpy numbers become plain Python numbers
        value = value.item()
    if isinstance(value, float):
        return round(value, 4) if math.isfinite(value) else None
    if isinstance(value, (int, bool)):
        return value
    return str(value)


@router.get("/{dataset_id}/preview", response_model=PreviewResponse)
def get_preview(dataset_id: str, rows: int = Query(default=20, ge=1, le=100)):
    df = file_service.load_clean_dataset(dataset_id)
    head = df.head(rows)
    return PreviewResponse(
        dataset_id=dataset_id,
        columns=[str(c) for c in head.columns],
        total_rows=int(len(df)),
        rows=[[_cell(v) for v in row] for row in head.itertuples(index=False, name=None)],
    )