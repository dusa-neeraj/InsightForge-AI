
import io
import logging
from pathlib import Path

import pandas as pd

from config import settings
from utils.errors import DatasetError

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


def validate_upload(filename: str | None, content: bytes) -> str:
    """Validate an upload provided as bytes. Returns its extension."""
    ext = Path(filename or "").suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise DatasetError("Only .csv and .xlsx files are supported.", 400)

    if len(content) == 0:
        raise DatasetError("The uploaded file is empty.", 400)

    if len(content) > settings.max_upload_bytes:
        raise DatasetError(
            f"File is too large. Maximum size is {settings.max_upload_mb} MB.",
            413,
        )

    return ext


def validate_upload_path(filename: str | None, path: Path) -> str:
    """Validate an upload saved on disk. Returns its extension."""
    ext = Path(filename or "").suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise DatasetError("Only .csv and .xlsx files are supported.", 400)

    try:
        size = path.stat().st_size
    except OSError:
        raise DatasetError("Could not access the uploaded file.", 400)

    if size == 0:
        raise DatasetError("The uploaded file is empty.", 400)

    if size > settings.max_upload_bytes:
        raise DatasetError(
            f"File is too large. Maximum size is {settings.max_upload_mb} MB.",
            413,
        )

    return ext


def _check_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.shape[1] == 0 or df.empty:
        raise DatasetError("The dataset has no rows to analyze.", 422)
    return df


def read_dataframe(content: bytes, ext: str) -> pd.DataFrame:
    """Read CSV/XLSX bytes into a DataFrame with friendly errors."""
    try:
        if ext == ".csv":
            try:
                df = pd.read_csv(io.BytesIO(content))
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(content), encoding="latin-1")
        else:
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")

        return _check_dataframe(df)

    except DatasetError:
        raise
    except pd.errors.EmptyDataError:
        raise DatasetError("The file contains no data.", 400)
    except Exception:
        logger.warning("Failed to read uploaded file", exc_info=True)
        raise DatasetError(
            "Could not read the file. It may be corrupted or badly formatted.",
            400,
        )


def read_dataframe_path(path: Path, ext: str) -> pd.DataFrame:
    """Read CSV/XLSX directly from disk without loading the raw file into bytes."""
    try:
        if ext == ".csv":
            try:
                df = pd.read_csv(path)
            except UnicodeDecodeError:
                df = pd.read_csv(path, encoding="latin-1")
        else:
            df = pd.read_excel(path, engine="openpyxl")

        return _check_dataframe(df)

    except DatasetError:
        raise
    except pd.errors.EmptyDataError:
        raise DatasetError("The file contains no data.", 400)
    except Exception:
        logger.warning("Failed to read uploaded file", exc_info=True)
        raise DatasetError(
            "Could not read the file. It may be corrupted or badly formatted.",
            400,
        )
