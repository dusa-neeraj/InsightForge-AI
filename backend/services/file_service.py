import json
import logging
import time
import warnings
from pathlib import Path
from typing import Any

import pandas as pd

from config import settings
from utils.errors import DatasetError
from utils.helpers import is_valid_dataset_id
from utils.validators import read_dataframe

logger = logging.getLogger(__name__)
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


def _write_dataset_files(
    folder: Path,
    clean_df: pd.DataFrame,
    cleaning_report: dict[str, Any],
) -> None:
    """Write cleaned data and report while logging each save sub-stage."""
    started = time.perf_counter()
    clean_path = folder / "clean.csv"
    clean_df.to_csv(clean_path, index=False)
    logger.info(
        "Dataset save stage=clean_csv_written rows=%s columns=%s bytes=%s elapsed=%.2fs",
        len(clean_df),
        len(clean_df.columns),
        clean_path.stat().st_size,
        time.perf_counter() - started,
    )

    report_started = time.perf_counter()
    report_path = folder / "cleaning_report.json"
    report_path.write_text(json.dumps(cleaning_report, default=str), encoding="utf-8")
    logger.info(
        "Dataset save stage=cleaning_report_written bytes=%s elapsed=%.2fs",
        report_path.stat().st_size,
        time.perf_counter() - report_started,
    )


def save_dataset(
    dataset_id: str,
    raw_content: bytes,
    ext: str,
    clean_df: pd.DataFrame,
    cleaning_report: dict[str, Any],
) -> None:
    total_started = time.perf_counter()
    folder = _dataset_dir(dataset_id)
    folder.mkdir(parents=True, exist_ok=True)

    raw_started = time.perf_counter()
    raw_path = folder / f"raw{ext}"
    raw_path.write_bytes(raw_content)
    logger.info(
        "Dataset save stage=raw_file_written bytes=%s elapsed=%.2fs",
        raw_path.stat().st_size,
        time.perf_counter() - raw_started,
    )

    _write_dataset_files(folder, clean_df, cleaning_report)
    logger.info("Dataset save stage=complete elapsed=%.2fs", time.perf_counter() - total_started)


def save_dataset_from_path(
    dataset_id: str,
    raw_path: Path,
    ext: str,
    clean_df: pd.DataFrame,
    cleaning_report: dict[str, Any],
) -> None:
    """Save a disk-based raw upload and its cleaned dataset."""
    total_started = time.perf_counter()
    folder = _dataset_dir(dataset_id)
    folder.mkdir(parents=True, exist_ok=True)

    destination = folder / f"raw{ext}"

    # Avoid copying the file when it is already at the destination.
    raw_started = time.perf_counter()
    if raw_path.resolve() != destination.resolve():
        import shutil
        shutil.copyfile(raw_path, destination)
        raw_action = "copied"
    else:
        raw_action = "already_at_destination"
    raw_size = destination.stat().st_size if destination.exists() else raw_path.stat().st_size
    logger.info(
        "Dataset save stage=raw_file_%s bytes=%s elapsed=%.2fs",
        raw_action,
        raw_size,
        time.perf_counter() - raw_started,
    )

    _write_dataset_files(folder, clean_df, cleaning_report)
    logger.info("Dataset save stage=complete elapsed=%.2fs", time.perf_counter() - total_started)


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


MAX_CHAT_TURNS = 20


def require_dataset(dataset_id: str) -> None:
    if not (_dataset_dir(dataset_id) / "clean.csv").exists():
        raise DatasetError("Dataset not found.", 404)


def _chat_file(dataset_id: str, session_id: str) -> Path:
    if not is_valid_dataset_id(session_id):
        raise DatasetError("Invalid session ID.", 400)
    return _dataset_dir(dataset_id) / "chat" / f"{session_id}.json"


def load_chat_history(dataset_id: str, session_id: str) -> list[dict[str, Any]]:
    path = _chat_file(dataset_id, session_id)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def append_chat_turn(dataset_id: str, session_id: str, turn: dict[str, Any]) -> None:
    path = _chat_file(dataset_id, session_id)
    history = load_chat_history(dataset_id, session_id)[-(MAX_CHAT_TURNS - 1):] + [turn]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, default=str), encoding="utf-8")
