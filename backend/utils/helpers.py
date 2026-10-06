import re
import uuid
from pathlib import Path

import pandas as pd


def new_dataset_id() -> str:
    return uuid.uuid4().hex  # 32 hex characters


def is_valid_dataset_id(value: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{32}", value or ""))


def safe_filename(name: str | None) -> str:
    """Keep only the base name and safe characters (used for display only)."""
    base = Path(name or "dataset").name
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)[:100]


def dataframe_preview(df: pd.DataFrame, rows: int = 10) -> list[dict[str, str]]:
    return df.head(rows).astype(str).to_dict(orient="records")