import json
import warnings
from pathlib import Path
from typing import Any

import pandas as pd

from config import settings
from utils.errors import DatasetError
from utils.helpers import is_valid_dataset_id
from utils.validators import read_dataframe

DATE_PATTERN = r"^\s*\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}"


def _dataset_dir(dataset_id: str) -> Path:
    if not is_valid_dataset_id(dataset_id):
        raise DatasetError("Invalid dataset ID.", 400)
    return settings.upload_dir / dataset_id


def _restore_dates(df: pd.DataFrame) -> pd.DataFrame:
    """CSV loses date types. Convert text columns that clearly hold dates."""
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
            continue
        text = series.dropna().astype(str)
        if text.empty or text.str.match(DATE_PATTERN).mean() < 0.9:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        if parsed.notna().sum() >= 0.9 * len(text):
            df[col] = parsed
    return df


def save_dataset(
    dataset_id: str,
    raw_content: bytes,
    ext: str,
    clean_df: pd.DataFrame,
    cleaning_report: dict[str, Any],
) -> None:
    folder = _dataset_dir(dataset_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"raw{ext}").write_bytes(raw_content)
    clean_df.to_csv(folder / "clean.csv", index=False)
    (folder / "cleaning_report.json").write_text(
        json.dumps(cleaning_report, default=str), encoding="utf-8"
    )


def load_clean_dataset(dataset_id: str) -> pd.DataFrame:
    path = _dataset_dir(dataset_id) / "clean.csv"
    if not path.exists():
        raise DatasetError("Dataset not found.", 404)
    return _restore_dates(pd.read_csv(path))


def load_raw_dataset(dataset_id: str) -> pd.DataFrame:
    folder = _dataset_dir(dataset_id)
    for ext in (".csv", ".xlsx"):
        path = folder / f"raw{ext}"
        if path.exists():
            return _restore_dates(read_dataframe(path.read_bytes(), ext))
    raise DatasetError("Dataset not found.", 404)


def load_cleaning_report(dataset_id: str) -> dict[str, Any]:
    path = _dataset_dir(dataset_id) / "cleaning_report.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
def save_insights(dataset_id: str, payload: dict[str, Any]) -> None:
    folder = _dataset_dir(dataset_id)
    (folder / "insights.json").write_text(json.dumps(payload, default=str), encoding="utf-8")


def load_insights(dataset_id: str) -> dict[str, Any] | None:
    path = _dataset_dir(dataset_id) / "insights.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))